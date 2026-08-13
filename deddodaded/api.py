from __future__ import annotations

import hmac
import re
import secrets
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from deddodaded.auth import AuthService, Session
from deddodaded.docker_manager import (
    DockerManager,
    DockerUnavailableError,
    RuntimeStatus,
)
from deddodaded.game_specs import (
    Game,
    ModReference,
    ServerConfig,
    build_container_spec,
)
from deddodaded.mods import (
    SteamWorkshopClient,
    ThunderstoreClient,
    ValheimModInstaller,
)
from deddodaded.schemas import (
    CreateServerRequest,
    LoginRequest,
    ValheimModRequest,
    WorkshopLookupRequest,
    ZomboidModRequest,
)
from deddodaded.settings import Settings
from deddodaded.storage import ServerRepository

SESSION_COOKIE = "deddodaded_session"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass(slots=True)
class AppServices:
    repository: ServerRepository
    auth: AuthService
    docker: DockerManager
    thunderstore: ThunderstoreClient
    workshop: SteamWorkshopClient
    valheim_installer: ValheimModInstaller


class LoginRateLimiter:
    def __init__(self, attempts: int = 5, window_seconds: int = 300) -> None:
        self.attempts = attempts
        self.window_seconds = window_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def retry_after(self, identity: str) -> int:
        now = time.monotonic()
        with self._lock:
            recent = [
                failure
                for failure in self._failures.get(identity, [])
                if now - failure < self.window_seconds
            ]
            self._failures[identity] = recent
            if len(recent) < self.attempts:
                return 0
            return max(1, int(self.window_seconds - (now - recent[0])))

    def failure(self, identity: str) -> None:
        with self._lock:
            self._failures.setdefault(identity, []).append(time.monotonic())

    def success(self, identity: str) -> None:
        with self._lock:
            self._failures.pop(identity, None)


def build_services(settings: Settings) -> AppServices:
    database_path = settings.data_root / "panel.db"
    repository = ServerRepository(database_path, settings.encryption_key)
    auth = AuthService(database_path)
    auth.bootstrap_from_file(
        settings.bootstrap_username,
        settings.bootstrap_password_file,
    )
    return AppServices(
        repository=repository,
        auth=auth,
        docker=DockerManager.connect(settings.data_root, settings.host_data_root),
        thunderstore=ThunderstoreClient(),
        workshop=SteamWorkshopClient(),
        valheim_installer=ValheimModInstaller(settings.data_root),
    )


def create_panel_app(
    settings: Settings,
    services: AppServices | None = None,
    static_directory: Path | None = None,
) -> FastAPI:
    services = services or build_services(settings)
    limiter = LoginRateLimiter()
    app = FastAPI(
        title="Deddodaded",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.services = services

    @app.middleware("http")
    async def security_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method in UNSAFE_METHODS and not _same_origin_request(request, settings):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Cross-site requests are not allowed"},
            )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' https://unpkg.com; "
            "style-src 'self' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; "
            "img-src 'self' data: https://shared.fastly.steamstatic.com "
            "https://cdn.cloudflare.steamstatic.com https://gcdn.thunderstore.io "
            "https://steamuserimages-a.akamaihd.net; connect-src 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def require_session(request: Request) -> Session:
        token = request.cookies.get(SESSION_COOKIE)
        session = services.auth.get_session(token) if token else None
        if session is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
        return session

    def require_csrf(
        request: Request,
        session: Session = Depends(require_session),
    ) -> Session:
        supplied_token = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(supplied_token, session.csrf_token):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid CSRF token")
        return session

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok" if services.docker.available else "degraded",
            "docker": services.docker.available,
        }

    @app.post("/api/auth/login")
    def login(body: LoginRequest, request: Request) -> Response:
        identity = request.client.host if request.client else "unknown"
        retry_after = limiter.retry_after(identity)
        if retry_after:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many login attempts",
                headers={"Retry-After": str(retry_after)},
            )
        if not services.auth.authenticate(body.username, body.password):
            limiter.failure(identity)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
        limiter.success(identity)
        token = services.auth.create_session(body.username)
        session = services.auth.get_session(token)
        assert session is not None
        response = JSONResponse(
            {"username": session.username, "csrf_token": session.csrf_token}
        )
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=43_200,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="strict",
            path="/",
        )
        return response

    @app.get("/api/auth/session")
    def session_info(
        session: Session = Depends(require_session),
    ) -> dict[str, str]:
        return {"username": session.username, "csrf_token": session.csrf_token}

    @app.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
    def logout(
        request: Request,
        session: Session = Depends(require_csrf),
    ) -> Response:
        del session
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            services.auth.revoke_session(token)
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    @app.get("/api/servers")
    def list_servers(
        session: Session = Depends(require_session),
    ) -> list[dict[str, Any]]:
        del session
        return [_server_payload(config, services) for config in services.repository.list_all()]

    @app.post("/api/servers", status_code=status.HTTP_201_CREATED)
    def create_server(
        body: CreateServerRequest,
        session: Session = Depends(require_csrf),
    ) -> dict[str, Any]:
        instance_id = _unique_instance_id(body.name, services.repository)
        config = ServerConfig(
            instance_id=instance_id,
            game=body.game,
            name=body.name,
            world_name=body.world_name,
            password=body.password,
            admin_password=body.admin_password,
            port=body.port,
            max_players=body.max_players,
            public=body.public,
        )
        build_container_spec(config, settings.host_data_root)
        if not services.repository.port_is_available(config.port):
            raise HTTPException(status.HTTP_409_CONFLICT, "That port range is already in use")
        services.repository.save(config)
        _deploy(config, services, f"Created by {session.username}")
        return _server_payload(config, services)

    @app.get("/api/servers/{instance_id}")
    def get_server(
        instance_id: str,
        session: Session = Depends(require_session),
    ) -> dict[str, Any]:
        del session
        return _server_payload(_require_server(instance_id, services), services)

    @app.post("/api/servers/{instance_id}/actions/{action}")
    def server_action(
        instance_id: str,
        action: str,
        session: Session = Depends(require_csrf),
    ) -> dict[str, Any]:
        config = _require_server(instance_id, services)
        actions: dict[str, Callable[[str], RuntimeStatus]] = {
            "start": services.docker.start,
            "stop": services.docker.stop,
            "restart": services.docker.restart,
            "redeploy": lambda _server_id: services.docker.deploy(config),
            "update": lambda _server_id: services.docker.deploy(config),
        }
        handler = actions.get(action)
        if handler is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown server action")
        try:
            runtime = handler(instance_id)
        except (DockerUnavailableError, KeyError) as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
        services.repository.add_event(
            instance_id, "info", f"{session.username} requested {action}"
        )
        return runtime.to_dict()

    @app.get("/api/servers/{instance_id}/logs")
    def server_logs(
        instance_id: str,
        session: Session = Depends(require_session),
        tail: int = Query(default=250, ge=1, le=1000),
    ) -> dict[str, str]:
        del session
        _require_server(instance_id, services)
        try:
            return {"logs": services.docker.logs(instance_id, tail)}
        except (DockerUnavailableError, KeyError) as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error

    @app.delete("/api/servers/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_server(
        instance_id: str,
        session: Session = Depends(require_csrf),
        delete_data: bool = Query(default=False),
    ) -> Response:
        _require_server(instance_id, services)
        try:
            services.docker.delete(instance_id, delete_data)
        except DockerUnavailableError as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
        services.repository.add_event(
            instance_id, "info", f"Deleted by {session.username}"
        )
        services.repository.delete(instance_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/mods/valheim/search")
    def search_valheim_mods(
        session: Session = Depends(require_session),
        q: str = Query(default="", max_length=100),
    ) -> list[dict[str, Any]]:
        del session
        try:
            return [asdict(package) for package in services.thunderstore.search(q)]
        except (httpx.HTTPError, ValueError) as error:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Thunderstore could not be reached"
            ) from error

    @app.post("/api/mods/project-zomboid/lookup")
    def lookup_workshop_item(
        body: WorkshopLookupRequest,
        session: Session = Depends(require_csrf),
    ) -> dict[str, Any]:
        del session
        try:
            return asdict(services.workshop.lookup(body.workshop_id))
        except LookupError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except (httpx.HTTPError, ValueError) as error:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Steam Workshop could not be reached"
            ) from error

    @app.post("/api/servers/{instance_id}/mods/valheim")
    def install_valheim_mod(
        instance_id: str,
        body: ValheimModRequest,
        session: Session = Depends(require_csrf),
    ) -> dict[str, Any]:
        config = _require_game(instance_id, Game.VALHEIM, services)
        try:
            packages = services.thunderstore.resolve_with_dependencies(body.package_id)
            existing = {mod.source_id: mod for mod in config.mods}
            for package in packages:
                services.valheim_installer.install(instance_id, package)
                existing[package.package_id] = package.as_mod_reference()
        except LookupError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except (httpx.HTTPError, ValueError) as error:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
        updated = replace(config, mods=tuple(existing.values()))
        services.repository.save(updated)
        _deploy(updated, services, f"{session.username} installed {body.package_id}")
        return _server_payload(updated, services)

    @app.post("/api/servers/{instance_id}/mods/project-zomboid")
    def install_zomboid_mod(
        instance_id: str,
        body: ZomboidModRequest,
        session: Session = Depends(require_csrf),
    ) -> dict[str, Any]:
        config = _require_game(instance_id, Game.PROJECT_ZOMBOID, services)
        mods = {mod.source_id: mod for mod in config.mods}
        mods[body.workshop_id] = ModReference(
            source_id=body.workshop_id,
            name=body.name,
            mod_id=body.mod_id,
        )
        updated = replace(config, mods=tuple(mods.values()))
        services.repository.save(updated)
        _deploy(updated, services, f"{session.username} installed {body.name}")
        return _server_payload(updated, services)

    @app.delete("/api/servers/{instance_id}/mods/{source_id}")
    def remove_mod(
        instance_id: str,
        source_id: str,
        session: Session = Depends(require_csrf),
    ) -> dict[str, Any]:
        config = _require_server(instance_id, services)
        if not any(mod.source_id == source_id for mod in config.mods):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Mod is not installed")
        if config.game is Game.VALHEIM:
            services.valheim_installer.uninstall(instance_id, source_id)
        updated = replace(
            config,
            mods=tuple(mod for mod in config.mods if mod.source_id != source_id),
        )
        services.repository.save(updated)
        _deploy(updated, services, f"{session.username} removed {source_id}")
        return _server_payload(updated, services)

    @app.get("/api/events")
    def recent_events(
        session: Session = Depends(require_session),
    ) -> list[dict[str, str | int | None]]:
        del session
        return services.repository.recent_events()

    frontend = static_directory or Path(__file__).with_name("static")
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app


def _same_origin_request(request: Request, settings: Settings) -> bool:
    fetch_site = request.headers.get("Sec-Fetch-Site", "").casefold()
    if fetch_site == "cross-site":
        return False
    origin = request.headers.get("Origin")
    if not origin:
        return True
    if settings.allowed_origin:
        return origin.rstrip("/") == settings.allowed_origin.rstrip("/")
    return urlparse(origin).netloc.casefold() == request.headers.get("Host", "").casefold()


def _unique_instance_id(name: str, repository: ServerRepository) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:36] or "server"
    candidate = base
    while repository.get(candidate) is not None:
        candidate = f"{base[:31]}-{secrets.token_hex(2)}"
    return candidate


def _require_server(instance_id: str, services: AppServices) -> ServerConfig:
    config = services.repository.get(instance_id)
    if config is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Server was not found")
    return config


def _require_game(
    instance_id: str, game: Game, services: AppServices
) -> ServerConfig:
    config = _require_server(instance_id, services)
    if config.game is not game:
        raise HTTPException(status.HTTP_409_CONFLICT, "That mod source does not match the game")
    return config


def _deploy(config: ServerConfig, services: AppServices, event: str) -> None:
    try:
        services.docker.deploy(config)
    except (DockerUnavailableError, ValueError) as error:
        services.repository.add_event(config.instance_id, "error", str(error))
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
    services.repository.add_event(config.instance_id, "info", event)


def _server_payload(config: ServerConfig, services: AppServices) -> dict[str, Any]:
    return {
        "id": config.instance_id,
        "game": config.game.value,
        "name": config.name,
        "world_name": config.world_name,
        "port": config.port,
        "port_end": config.port + (2 if config.game is Game.VALHEIM else 1),
        "max_players": config.max_players,
        "public": config.public,
        "mods": [
            {
                "source_id": mod.source_id,
                "name": mod.name,
                "mod_id": mod.mod_id,
                "version": mod.version,
            }
            for mod in config.mods
        ],
        "runtime": services.docker.status(config.instance_id).to_dict(),
    }
