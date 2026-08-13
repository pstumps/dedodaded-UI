from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from unittest import TestCase

from docker.errors import NotFound

from dedodaded.docker_manager import DockerManager, DockerUnavailableError
from dedodaded.game_specs import Game, ServerConfig


class FakeContainer:
    def __init__(self, name: str, status: str = "created") -> None:
        self.name = name
        self.status = status
        self.attrs = {"State": {"Status": status, "StartedAt": "", "Error": ""}}
        self.removed = False

    def start(self) -> None:
        self.status = "running"
        self.attrs["State"]["Status"] = "running"

    def stop(self, timeout: int) -> None:
        self.status = "exited"
        self.attrs["State"]["Status"] = "exited"

    def restart(self, timeout: int) -> None:
        self.start()

    def remove(self, force: bool) -> None:
        self.removed = True

    def reload(self) -> None:
        pass

    def logs(self, **kwargs: object) -> bytes:
        return b"server ready\n"


class FakeContainers:
    def __init__(self) -> None:
        self.items: dict[str, FakeContainer] = {}
        self.last_create: dict[str, object] = {}

    def get(self, name: str) -> FakeContainer:
        container = self.items.get(name)
        if container is None or container.removed:
            raise NotFound("missing")
        return container

    def create(self, **options: object) -> FakeContainer:
        self.last_create = options
        container = FakeContainer(str(options["name"]))
        self.items[container.name] = container
        return container


class FakeImages:
    def __init__(self) -> None:
        self.pulled: list[str] = []

    def pull(self, image: str) -> None:
        self.pulled.append(image)


class FakeClient:
    def __init__(self) -> None:
        self.containers = FakeContainers()
        self.images = FakeImages()


def valheim_config() -> ServerConfig:
    return ServerConfig(
        instance_id="mistlands",
        game=Game.VALHEIM,
        name="Mistlands Club",
        world_name="Mistlands",
        password="secret",
        admin_password="unused",
        port=2456,
        max_players=10,
    )


class DockerManagerTests(TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.client = FakeClient()
        self.manager = DockerManager(
            self.client,
            Path(self.temporary_directory.name),
            PurePosixPath("/opt/dedodaded/data"),
        )

    def test_deploy_pulls_creates_and_starts_managed_container(self) -> None:
        status = self.manager.deploy(valheim_config())

        self.assertEqual(status.state, "running")
        self.assertEqual(
            self.client.images.pulled,
            ["ghcr.io/community-valheim-tools/valheim-server:latest"],
        )
        options = self.client.containers.last_create
        self.assertEqual(options["name"], "dedodaded-mistlands")
        self.assertEqual(
            options["labels"]["com.dedodaded.instance-id"],  # type: ignore[index]
            "mistlands",
        )
        self.assertTrue(
            (Path(self.temporary_directory.name) / "instances/mistlands/config").is_dir()
        )

    def test_deploy_replaces_existing_container_but_keeps_data(self) -> None:
        self.manager.deploy(valheim_config())
        existing = self.client.containers.get("dedodaded-mistlands")

        self.manager.deploy(valheim_config())

        self.assertTrue(existing.removed)
        self.assertTrue(
            (Path(self.temporary_directory.name) / "instances/mistlands/config").is_dir()
        )

    def test_actions_and_logs_target_managed_name(self) -> None:
        self.manager.deploy(valheim_config())

        self.assertEqual(self.manager.stop("mistlands").state, "exited")
        self.assertEqual(self.manager.start("mistlands").state, "running")
        self.assertEqual(self.manager.logs("mistlands"), "server ready\n")

    def test_unavailable_manager_returns_status_and_rejects_mutation(self) -> None:
        manager = DockerManager(
            None,
            Path(self.temporary_directory.name),
            PurePosixPath("/opt/dedodaded/data"),
            "socket missing",
        )

        self.assertEqual(manager.status("mistlands").state, "unavailable")
        with self.assertRaisesRegex(DockerUnavailableError, "socket missing"):
            manager.deploy(valheim_config())
