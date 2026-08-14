from dataclasses import replace
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from unittest import TestCase

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from dedodaded.api import AppServices, create_panel_app
from dedodaded.auth import AuthService
from dedodaded.docker_manager import RuntimeStatus
from dedodaded.game_specs import ServerConfig
from dedodaded.mods import WorkshopItem
from dedodaded.settings import Settings
from dedodaded.storage import ServerRepository


class StubDocker:
    available = True
    connection_error = None

    def __init__(self) -> None:
        self.deployed: list[ServerConfig] = []

    def deploy(self, config: ServerConfig) -> RuntimeStatus:
        self.deployed.append(config)
        return RuntimeStatus("running")

    def status(self, instance_id: str) -> RuntimeStatus:
        return RuntimeStatus("running" if self.deployed else "not-created")

    def start(self, instance_id: str) -> RuntimeStatus:
        return RuntimeStatus("running")

    def stop(self, instance_id: str) -> RuntimeStatus:
        return RuntimeStatus("exited")

    def restart(self, instance_id: str) -> RuntimeStatus:
        return RuntimeStatus("running")

    def delete(self, instance_id: str, delete_data: bool = False) -> None:
        pass

    def logs(self, instance_id: str, tail: int) -> str:
        return "server ready"


class StubThunderstore:
    def search(self, query: str):  # type: ignore[no-untyped-def]
        return []


class StubWorkshop:
    def lookup(self, workshop_id: str) -> WorkshopItem:
        return WorkshopItem(workshop_id, "Mod Options", "Shared settings", None)


class StubInstaller:
    def install(self, instance_id: str, package: object) -> None:
        pass

    def uninstall(self, instance_id: str, package_id: str) -> None:
        pass


class ApiTests(TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        root = Path(self.temporary_directory.name)
        key = Fernet.generate_key().decode()
        settings = Settings(
            data_root=root,
            host_data_root=PurePosixPath("/opt/dedodaded/data"),
            encryption_key=key,
            bootstrap_username="admin",
            bootstrap_password_file=root / "unused",
            cookie_secure=False,
            allowed_origin=None,
        )
        self.settings = settings
        repository = ServerRepository(root / "panel.db", key)
        auth = AuthService(root / "panel.db", iterations=1_000)
        auth.create_user("admin", "a-long-test-password")
        self.docker = StubDocker()
        services = AppServices(
            repository=repository,
            auth=auth,
            docker=self.docker,  # type: ignore[arg-type]
            thunderstore=StubThunderstore(),  # type: ignore[arg-type]
            workshop=StubWorkshop(),  # type: ignore[arg-type]
            valheim_installer=StubInstaller(),  # type: ignore[arg-type]
        )
        self.services = services
        self.client = TestClient(create_panel_app(settings, services))
        self.addCleanup(self.client.close)

    def login(self) -> str:
        response = self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "a-long-test-password"},
        )
        self.assertEqual(response.status_code, 200)
        return str(response.json()["csrf_token"])

    def test_health_is_public_but_server_list_requires_login(self) -> None:
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.client.get("/api/servers").status_code, 401)

    def test_login_and_csrf_protect_mutations(self) -> None:
        self.login()

        response = self.client.post("/api/servers", json={})

        self.assertEqual(response.status_code, 403)

    def test_creates_server_without_returning_secrets(self) -> None:
        csrf_token = self.login()

        response = self.client.post(
            "/api/servers",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "game": "project-zomboid",
                "name": "Knox County",
                "world_name": "Knox",
                "password": "survive",
                "admin_password": "Admin1234",
                "port": 16261,
                "max_players": 16,
                "public": True,
            },
        )

        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["runtime"]["state"], "running")
        self.assertNotIn("password", response.text)
        self.assertEqual(self.docker.deployed[0].admin_password, "Admin1234")

    def test_installs_project_zomboid_mod_and_redeploys(self) -> None:
        csrf_token = self.login()
        created = self.client.post(
            "/api/servers",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "game": "project-zomboid",
                "name": "Knox County",
                "world_name": "Knox",
                "password": "survive",
                "admin_password": "Admin1234",
                "port": 16261,
                "max_players": 16,
                "public": True,
            },
        ).json()

        response = self.client.post(
            f"/api/servers/{created['id']}/mods/project-zomboid",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "workshop_id": "2169435993",
                "name": "Mod Options",
                "mod_id": "modoptions",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["mods"][0]["source_id"], "2169435993")
        self.assertEqual(len(self.docker.deployed), 2)

    def test_rejects_cross_site_login(self) -> None:
        response = self.client.post(
            "/api/auth/login",
            headers={"Sec-Fetch-Site": "cross-site", "Origin": "https://attacker.test"},
            json={"username": "admin", "password": "a-long-test-password"},
        )

        self.assertEqual(response.status_code, 403)

    def test_https_prefix_scopes_routes_origin_and_cookie(self) -> None:
        settings = replace(
            self.settings,
            allowed_origin="https://192.0.2.10",
            base_path="/dedodaded",
            cookie_secure=True,
        )
        with TestClient(
            create_panel_app(settings, self.services),
            base_url="https://192.0.2.10",
        ) as client:
            index = client.get("/dedodaded/")
            self.assertEqual(index.status_code, 200)
            self.assertIn('href="styles.css"', index.text)
            self.assertIn('src="app.js"', index.text)
            self.assertEqual(client.get("/dedodaded/app.js").status_code, 200)
            health = client.get("/dedodaded/api/health")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.headers["cache-control"], "no-store")
            self.assertEqual(client.get("/api/health").status_code, 404)
            rejected = client.post(
                "/dedodaded/api/auth/login",
                headers={"Origin": "https://attacker.test"},
                json={"username": "admin", "password": "a-long-test-password"},
            )
            self.assertEqual(rejected.status_code, 403)

            response = client.post(
                "/dedodaded/api/auth/login",
                headers={"Origin": "https://192.0.2.10"},
                json={"username": "admin", "password": "a-long-test-password"},
            )

        self.assertEqual(response.status_code, 200)
        cookie = response.headers["set-cookie"].casefold()
        self.assertIn("path=/dedodaded", cookie)
        self.assertIn("secure", cookie)
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=strict", cookie)
