from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Session:
    username: str
    csrf_token: str
    expires_at: datetime


class AuthService:
    def __init__(self, database_path: Path, iterations: int = 600_000) -> None:
        self.database_path = database_path
        self.iterations = iterations
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    csrf_token TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
        with suppress(PermissionError):
            self.database_path.chmod(0o600)

    def bootstrap_from_file(self, username: str, password_file: Path) -> bool:
        if self.has_users():
            return False
        if not password_file.is_file():
            raise RuntimeError(
                "No panel administrator exists and the bootstrap password file is missing"
            )
        password = password_file.read_text(encoding="utf-8").rstrip("\r\n")
        if len(password) < 12:
            raise ValueError("The panel administrator password must contain at least 12 characters")
        self.create_user(username, password)
        password_file.unlink()
        return True

    def has_users(self) -> bool:
        with self._connection() as connection:
            return connection.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    def create_user(self, username: str, password: str) -> None:
        normalized_username = username.strip()
        if not normalized_username:
            raise ValueError("Username cannot be empty")
        if len(password) < 12:
            raise ValueError("Password must contain at least 12 characters")
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (
                    normalized_username,
                    self._hash_password(password),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def authenticate(self, username: str, password: str) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT password_hash FROM users WHERE username = ? COLLATE NOCASE",
                (username.strip(),),
            ).fetchone()
        if row is None:
            self._hash_password(password)
            return False
        return self._verify_password(password, str(row["password_hash"]))

    def create_session(self, username: str, lifetime: timedelta = timedelta(hours=12)) -> str:
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        with self._connection() as connection:
            user = connection.execute(
                "SELECT id FROM users WHERE username = ? COLLATE NOCASE", (username.strip(),)
            ).fetchone()
            if user is None:
                raise KeyError(username)
            connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now.isoformat(),))
            connection.execute(
                """
                INSERT INTO sessions (
                    token_hash, user_id, csrf_token, expires_at, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    self._token_hash(token),
                    int(user["id"]),
                    secrets.token_urlsafe(24),
                    (now + lifetime).isoformat(),
                    now.isoformat(),
                ),
            )
        return token

    def get_session(self, token: str) -> Session | None:
        now = datetime.now(UTC)
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT users.username, sessions.csrf_token, sessions.expires_at
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = ?
                """,
                (self._token_hash(token),),
            ).fetchone()
            if row is None:
                return None
            expires_at = datetime.fromisoformat(str(row["expires_at"]))
            if expires_at <= now:
                connection.execute(
                    "DELETE FROM sessions WHERE token_hash = ?", (self._token_hash(token),)
                )
                return None
        return Session(str(row["username"]), str(row["csrf_token"]), expires_at)

    def revoke_session(self, token: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE token_hash = ?", (self._token_hash(token),)
            )

    def _hash_password(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, self.iterations
        )
        return "$".join(
            (
                "pbkdf2_sha256",
                str(self.iterations),
                base64.urlsafe_b64encode(salt).decode("ascii"),
                base64.urlsafe_b64encode(digest).decode("ascii"),
            )
        )

    @staticmethod
    def _verify_password(password: str, encoded: str) -> bool:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            base64.urlsafe_b64decode(salt),
            int(iterations),
        )
        return hmac.compare_digest(
            base64.urlsafe_b64encode(digest).decode("ascii"), expected
        )

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
