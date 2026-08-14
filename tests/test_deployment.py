from pathlib import Path
from unittest import TestCase


class DeploymentConfigTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).parents[1]
        cls.base_compose = (root / "compose.yaml").read_text(encoding="utf-8")
        cls.private_compose = (root / "compose.private.yaml").read_text(encoding="utf-8")
        cls.https_compose = (root / "compose.https.yaml").read_text(encoding="utf-8")
        cls.caddyfile = (root / "Caddyfile").read_text(encoding="utf-8")
        cls.installer = (root / "install.sh").read_text(encoding="utf-8")

    def test_https_mode_publishes_only_tls(self) -> None:
        self.assertNotIn("ports:", self.base_compose)
        self.assertIn("image: caddy:2.11.4-alpine", self.https_compose)
        self.assertIn("depends_on:\n      - panel", self.https_compose)
        self.assertIn('"443:443/tcp"', self.https_compose)
        self.assertNotIn('"80:80', self.https_compose)
        self.assertNotIn('"8080:8080', self.https_compose)

    def test_caddy_uses_short_lived_ip_certificate_without_http_challenge(self) -> None:
        self.assertIn("default_sni {$PANEL_PUBLIC_IP}", self.caddyfile)
        self.assertIn("profile shortlived", self.caddyfile)
        self.assertIn("disable_http_challenge", self.caddyfile)
        self.assertIn("auto_https disable_redirects", self.caddyfile)
        self.assertIn("reverse_proxy panel:8080", self.caddyfile)

    def test_installer_has_no_direct_public_http_mode(self) -> None:
        self.assertIn('ask "Access mode (private/https)"', self.installer)
        self.assertIn("COMPOSE_FILE=$compose_file", self.installer)
        self.assertIn(
            '-f "$APP_DIR/compose.yaml" -f "$APP_DIR/$compose_override"',
            self.installer,
        )
        self.assertNotIn("none for direct HTTP", self.installer)
        self.assertNotIn("http://YOUR_VPS_IP", self.installer)

    def test_private_mode_maps_the_selected_tunnel_port_to_the_panel(self) -> None:
        self.assertIn(
            '"127.0.0.1:${PANEL_HTTP_PORT:-8080}:8080"',
            self.private_compose,
        )
        self.assertIn(
            "ssh -L $panel_port:127.0.0.1:$panel_port YOUR_USER@YOUR_VPS",
            self.installer,
        )