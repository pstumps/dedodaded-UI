import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from deddodaded.auth import AuthService


class AuthServiceTests(TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.database_path = self.root / "panel.db"
        self.auth = AuthService(self.database_path, iterations=1_000)

    def test_bootstrap_hashes_password_and_removes_plaintext_file(self) -> None:
        password_file = self.root / "bootstrap_password"
        password_file.write_text("a-long-test-password\n", encoding="utf-8")

        created = self.auth.bootstrap_from_file("admin", password_file)

        self.assertTrue(created)
        self.assertFalse(password_file.exists())
        self.assertTrue(self.auth.authenticate("ADMIN", "a-long-test-password"))
        self.assertFalse(self.auth.authenticate("admin", "wrong-password"))
        self.assertNotIn(b"a-long-test-password", self.database_path.read_bytes())

    def test_session_uses_hashed_token_and_separate_csrf_token(self) -> None:
        self.auth.create_user("admin", "a-long-test-password")

        token = self.auth.create_session("admin")
        session = self.auth.get_session(token)

        self.assertIsNotNone(session)
        assert session is not None
        self.assertNotEqual(session.csrf_token, token)
        self.assertNotIn(token, self.database_path.read_text(encoding="latin-1"))

    def test_expired_session_is_rejected(self) -> None:
        self.auth.create_user("admin", "a-long-test-password")
        token = self.auth.create_session("admin", lifetime=timedelta(seconds=1))
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute(
                "UPDATE sessions SET expires_at = ?",
                ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(),),
            )
            connection.commit()

        self.assertIsNone(self.auth.get_session(token))

    def test_bootstrap_fails_closed_without_password_file(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "bootstrap password file is missing"):
            self.auth.bootstrap_from_file("admin", self.root / "missing")
