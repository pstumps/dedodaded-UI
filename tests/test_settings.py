import os
from unittest import TestCase
from unittest.mock import patch

from cryptography.fernet import Fernet

from dedodaded.settings import Settings


class SettingsTests(TestCase):
    def test_normalizes_configured_base_path(self) -> None:
        environment = {
            "PANEL_BASE_PATH": "//dedodaded//",
            "PANEL_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        }

        with patch.dict(os.environ, environment, clear=True):
            settings = Settings.from_env()

        self.assertEqual(settings.base_path, "/dedodaded")

    def test_slash_only_base_path_uses_root(self) -> None:
        environment = {
            "PANEL_BASE_PATH": "///",
            "PANEL_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        }

        with patch.dict(os.environ, environment, clear=True):
            settings = Settings.from_env()

        self.assertEqual(settings.base_path, "")