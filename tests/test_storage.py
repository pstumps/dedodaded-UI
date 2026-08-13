from tempfile import TemporaryDirectory
from unittest import TestCase

from cryptography.fernet import Fernet

from deddodaded.game_specs import Game, ModReference, ServerConfig
from deddodaded.storage import ServerRepository


class ServerRepositoryTests(TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        database_path = __import__("pathlib").Path(self.temporary_directory.name) / "panel.db"
        self.repository = ServerRepository(database_path, Fernet.generate_key().decode())

    def test_round_trips_encrypted_server_config_and_mods(self) -> None:
        config = ServerConfig(
            instance_id="knox",
            game=Game.PROJECT_ZOMBOID,
            name="Knox County",
            world_name="unused",
            password="survive",
            admin_password="admin-secret",
            port=16261,
            max_players=16,
            mods=(ModReference("2169435993", "Mod Options", "modoptions"),),
        )

        self.repository.save(config)

        self.assertEqual(self.repository.get("knox"), config)
        database_bytes = self.repository.database_path.read_bytes()
        self.assertNotIn(b"survive", database_bytes)
        self.assertNotIn(b"admin-secret", database_bytes)

    def test_detects_overlapping_three_port_ranges(self) -> None:
        config = ServerConfig(
            instance_id="mistlands",
            game=Game.VALHEIM,
            name="Mistlands",
            world_name="Mistlands",
            password="secret",
            admin_password="unused",
            port=2456,
            max_players=10,
        )
        self.repository.save(config)

        self.assertFalse(self.repository.port_is_available(2458))
        self.assertTrue(self.repository.port_is_available(2461))
        self.assertTrue(self.repository.port_is_available(2458, exclude_id="mistlands"))

    def test_delete_cascades_mods(self) -> None:
        config = ServerConfig(
            instance_id="knox",
            game=Game.PROJECT_ZOMBOID,
            name="Knox County",
            world_name="unused",
            password="survive",
            admin_password="admin-secret",
            port=16261,
            max_players=16,
            mods=(ModReference("2169435993", "Mod Options", "modoptions"),),
        )
        self.repository.save(config)

        self.assertTrue(self.repository.delete("knox"))
        self.assertIsNone(self.repository.get("knox"))
