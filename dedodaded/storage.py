from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from cryptography.fernet import Fernet

from dedodaded.game_specs import Game, ModReference, ServerConfig


class ServerRepository:
    def __init__(self, database_path: Path, encryption_key: str) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._cipher = Fernet(encryption_key.encode("ascii"))
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
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
                CREATE TABLE IF NOT EXISTS servers (
                    id TEXT PRIMARY KEY,
                    game TEXT NOT NULL,
                    name TEXT NOT NULL,
                    world_name TEXT NOT NULL,
                    password TEXT NOT NULL,
                    admin_password TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    max_players INTEGER NOT NULL,
                    public INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mods (
                    server_id TEXT NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
                    source_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    mod_id TEXT,
                    download_url TEXT,
                    version TEXT,
                    installed_at TEXT NOT NULL,
                    PRIMARY KEY (server_id, source_id)
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    server_id TEXT REFERENCES servers(id) ON DELETE CASCADE,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            mod_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(mods)").fetchall()
            }
            if "version" not in mod_columns:
                connection.execute("ALTER TABLE mods ADD COLUMN version TEXT")

    def save(self, config: ServerConfig) -> None:
        now = datetime.now(UTC).isoformat()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO servers (
                    id, game, name, world_name, password, admin_password, port,
                    max_players, public, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    game = excluded.game,
                    name = excluded.name,
                    world_name = excluded.world_name,
                    password = excluded.password,
                    admin_password = excluded.admin_password,
                    port = excluded.port,
                    max_players = excluded.max_players,
                    public = excluded.public,
                    updated_at = excluded.updated_at
                """,
                (
                    config.instance_id,
                    config.game.value,
                    config.name,
                    config.world_name,
                    self._encrypt(config.password),
                    self._encrypt(config.admin_password),
                    config.port,
                    config.max_players,
                    int(config.public),
                    now,
                    now,
                ),
            )
            connection.execute("DELETE FROM mods WHERE server_id = ?", (config.instance_id,))
            connection.executemany(
                """
                INSERT INTO mods (
                    server_id, source_id, name, mod_id, download_url, version, installed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        config.instance_id,
                        mod.source_id,
                        mod.name,
                        mod.mod_id,
                        mod.download_url,
                        mod.version,
                        now,
                    )
                    for mod in config.mods
                ],
            )

    def get(self, instance_id: str) -> ServerConfig | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM servers WHERE id = ?", (instance_id,)
            ).fetchone()
            if row is None:
                return None
            mods = connection.execute(
                "SELECT * FROM mods WHERE server_id = ? ORDER BY installed_at, source_id",
                (instance_id,),
            ).fetchall()
        return self._to_config(row, mods)

    def list_all(self) -> list[ServerConfig]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM servers ORDER BY created_at").fetchall()
            mod_rows = connection.execute(
                "SELECT * FROM mods ORDER BY installed_at, source_id"
            ).fetchall()
        mods_by_server: dict[str, list[sqlite3.Row]] = {}
        for mod_row in mod_rows:
            mods_by_server.setdefault(str(mod_row["server_id"]), []).append(mod_row)
        return [self._to_config(row, mods_by_server.get(str(row["id"]), [])) for row in rows]

    def delete(self, instance_id: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM servers WHERE id = ?", (instance_id,))
        return cursor.rowcount > 0

    def port_is_available(self, port: int, exclude_id: str | None = None) -> bool:
        parameters: list[str | int] = [port - 2, port + 2]
        query = "SELECT 1 FROM servers WHERE port BETWEEN ? AND ?"
        if exclude_id is not None:
            query += " AND id != ?"
            parameters.append(exclude_id)
        with self._connection() as connection:
            return connection.execute(query, parameters).fetchone() is None

    def add_event(self, instance_id: str | None, level: str, message: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO events (server_id, level, message, created_at) VALUES (?, ?, ?, ?)",
                (instance_id, level, message, datetime.now(UTC).isoformat()),
            )

    def recent_events(self, limit: int = 20) -> list[dict[str, str | int | None]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def _to_config(
        self, row: sqlite3.Row, mod_rows: list[sqlite3.Row]
    ) -> ServerConfig:
        return ServerConfig(
            instance_id=str(row["id"]),
            game=Game(str(row["game"])),
            name=str(row["name"]),
            world_name=str(row["world_name"]),
            password=self._decrypt(str(row["password"])),
            admin_password=self._decrypt(str(row["admin_password"])),
            port=int(row["port"]),
            max_players=int(row["max_players"]),
            public=bool(row["public"]),
            mods=tuple(
                ModReference(
                    source_id=str(mod["source_id"]),
                    name=str(mod["name"]),
                    mod_id=str(mod["mod_id"]) if mod["mod_id"] is not None else None,
                    download_url=(
                        str(mod["download_url"])
                        if mod["download_url"] is not None
                        else None
                    ),
                    version=str(mod["version"]) if mod["version"] is not None else None,
                )
                for mod in mod_rows
            ),
        )

    def _encrypt(self, value: str) -> str:
        return self._cipher.encrypt(value.encode()).decode("ascii")

    def _decrypt(self, value: str) -> str:
        return self._cipher.decrypt(value.encode("ascii")).decode()
