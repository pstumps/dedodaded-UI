from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import docker
from docker.errors import DockerException, NotFound

from deddodaded.game_specs import Game, ServerConfig, build_container_spec


class DockerUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RuntimeStatus:
    state: str
    detail: str | None = None
    started_at: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


class DockerManager:
    def __init__(
        self,
        client: Any | None,
        local_data_root: Path,
        host_data_root: PurePosixPath,
        connection_error: str | None = None,
    ) -> None:
        self.client = client
        self.local_data_root = local_data_root
        self.host_data_root = host_data_root
        self.connection_error = connection_error

    @classmethod
    def connect(
        cls, local_data_root: Path, host_data_root: PurePosixPath
    ) -> DockerManager:
        try:
            client = docker.from_env()
            client.ping()
        except DockerException as error:
            return cls(None, local_data_root, host_data_root, str(error))
        return cls(client, local_data_root, host_data_root)

    @property
    def available(self) -> bool:
        return self.client is not None

    def deploy(self, config: ServerConfig) -> RuntimeStatus:
        client = self._require_client()
        spec = build_container_spec(config, self.host_data_root)
        self._prepare_directories(config)
        client.images.pull(spec.image)

        existing = self._get_container(config.instance_id)
        if existing is not None:
            existing.remove(force=True)

        create_options: dict[str, Any] = {
            "image": spec.image,
            "name": self._container_name(config.instance_id),
            "environment": spec.environment,
            "ports": spec.ports,
            "volumes": spec.volumes,
            "detach": True,
            "labels": {
                "com.deddodaded.managed": "true",
                "com.deddodaded.instance-id": config.instance_id,
                "com.deddodaded.game": config.game.value,
            },
            "restart_policy": {"Name": "unless-stopped"},
            "stop_timeout": spec.stop_timeout,
        }
        if spec.cap_add:
            create_options["cap_add"] = list(spec.cap_add)

        container = client.containers.create(**create_options)
        container.start()
        return self.status(config.instance_id)

    def start(self, instance_id: str) -> RuntimeStatus:
        container = self._require_container(instance_id)
        container.start()
        return self.status(instance_id)

    def stop(self, instance_id: str) -> RuntimeStatus:
        container = self._require_container(instance_id)
        container.stop(timeout=120)
        return self.status(instance_id)

    def restart(self, instance_id: str) -> RuntimeStatus:
        container = self._require_container(instance_id)
        container.restart(timeout=120)
        return self.status(instance_id)

    def delete(self, instance_id: str, delete_data: bool = False) -> None:
        container = self._get_container(instance_id)
        if container is not None:
            container.remove(force=True)
        if delete_data:
            shutil.rmtree(self.local_data_root / "instances" / instance_id, ignore_errors=True)

    def status(self, instance_id: str) -> RuntimeStatus:
        if self.client is None:
            return RuntimeStatus("unavailable", self.connection_error)
        container = self._get_container(instance_id)
        if container is None:
            return RuntimeStatus("not-created")
        try:
            container.reload()
            state = container.attrs.get("State", {})
            return RuntimeStatus(
                state=str(state.get("Status", container.status or "unknown")),
                detail=str(state.get("Error")) if state.get("Error") else None,
                started_at=(
                    str(state.get("StartedAt")) if state.get("StartedAt") else None
                ),
            )
        except DockerException as error:
            return RuntimeStatus("error", str(error))

    def logs(self, instance_id: str, tail: int = 250) -> str:
        container = self._require_container(instance_id)
        output = container.logs(tail=max(1, min(tail, 1000)), timestamps=True)
        if isinstance(output, bytes):
            return output.decode("utf-8", errors="replace")
        return str(output)

    def _prepare_directories(self, config: ServerConfig) -> None:
        instance_root = self.local_data_root / "instances" / config.instance_id
        directories = (instance_root / "config", instance_root / "server")
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
        if config.game is Game.PROJECT_ZOMBOID:
            for directory in directories:
                try:
                    directory.chmod(0o775)
                    shutil.chown(directory, user=1000, group=1000)
                except (LookupError, PermissionError):
                    pass

    def _require_client(self) -> Any:
        if self.client is None:
            raise DockerUnavailableError(self.connection_error or "Docker is unavailable")
        return self.client

    def _get_container(self, instance_id: str) -> Any | None:
        client = self._require_client()
        try:
            return client.containers.get(self._container_name(instance_id))
        except NotFound:
            return None

    def _require_container(self, instance_id: str) -> Any:
        container = self._get_container(instance_id)
        if container is None:
            raise KeyError(f"Server container {instance_id!r} does not exist")
        return container

    @staticmethod
    def _container_name(instance_id: str) -> str:
        return f"deddodaded-{instance_id}"
