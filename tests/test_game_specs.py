from unittest import TestCase

from dedodaded.game_specs import Game, ModReference, ServerConfig, build_container_spec


class GameSpecTests(TestCase):
    def test_valheim_uses_three_udp_ports_and_bepinex_for_mods(self) -> None:
        config = ServerConfig(
            instance_id="mistlands",
            game=Game.VALHEIM,
            name="Mistlands Club",
            world_name="Mistlands",
            password="secret",
            admin_password="unused",
            port=2456,
            max_players=10,
            mods=(ModReference("Azumatt-AzuClock", "AzuClock"),),
        )

        spec = build_container_spec(config, "/srv/dedodaded")

        self.assertEqual(spec.environment["BEPINEX"], "true")
        self.assertEqual(spec.ports["2458/udp"], 2458)
        self.assertIn("/srv/dedodaded/instances/mistlands/config", spec.volumes)

    def test_valheim_rejects_short_passwords(self) -> None:
        config = ServerConfig(
            instance_id="short",
            game=Game.VALHEIM,
            name="Short",
            world_name="Short",
            password="four",
            admin_password="unused",
            port=2456,
            max_players=10,
        )

        with self.assertRaisesRegex(ValueError, "at least 5"):
            build_container_spec(config, "/srv/dedodaded")

    def test_valheim_maps_non_default_ports_inside_and_outside_container(self) -> None:
        config = ServerConfig(
            instance_id="custom-valheim-port",
            game=Game.VALHEIM,
            name="Custom Valheim",
            world_name="Custom",
            password="secret",
            admin_password="unused",
            port=2500,
            max_players=10,
        )

        spec = build_container_spec(config, "/srv/dedodaded")

        self.assertEqual(spec.environment["SERVER_PORT"], "2500")
        self.assertEqual(
            spec.ports,
            {"2500/udp": 2500, "2501/udp": 2501, "2502/udp": 2502},
        )

    def test_zomboid_maps_workshop_and_internal_mod_ids(self) -> None:
        config = ServerConfig(
            instance_id="knox",
            game=Game.PROJECT_ZOMBOID,
            name="Knox County",
            world_name="unused",
            password="survive",
            admin_password="admin-secret",
            port=16261,
            max_players=16,
            mods=(
                ModReference("2169435993", "Mod Options", "modoptions"),
                ModReference("2286124931", "Better Sorting", "BetterSortCC"),
            ),
        )

        spec = build_container_spec(config, "/srv/dedodaded")

        self.assertEqual(spec.environment["MOD_WORKSHOP_IDS"], "2169435993;2286124931")
        self.assertEqual(spec.environment["MOD_NAMES"], "modoptions;BetterSortCC")
        self.assertEqual(spec.ports, {"16261/udp": 16261, "16262/udp": 16262})

    def test_zomboid_requires_internal_mod_id(self) -> None:
        config = ServerConfig(
            instance_id="invalid-mod",
            game=Game.PROJECT_ZOMBOID,
            name="Invalid",
            world_name="unused",
            password="survive",
            admin_password="admin-secret",
            port=16261,
            max_players=16,
            mods=(ModReference("2169435993", "Mod Options"),),
        )

        with self.assertRaisesRegex(ValueError, "Workshop ID and mod ID"):
            build_container_spec(config, "/srv/dedodaded")

    def test_zomboid_maps_non_default_ports_inside_and_outside_container(self) -> None:
        config = ServerConfig(
            instance_id="custom-zomboid-port",
            game=Game.PROJECT_ZOMBOID,
            name="Custom Zomboid",
            world_name="unused",
            password="survive",
            admin_password="admin-secret",
            port=17000,
            max_players=16,
        )

        spec = build_container_spec(config, "/srv/dedodaded")

        self.assertEqual(spec.environment["DEFAULT_PORT"], "17000")
        self.assertEqual(spec.environment["UDP_PORT"], "17001")
        self.assertEqual(spec.ports, {"17000/udp": 17000, "17001/udp": 17001})
