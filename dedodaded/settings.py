from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from cryptography.fernet import Fernet


@dataclass(frozen=True, slots=True)
class Settings:
    data_root: Path
    host_data_root: PurePosixPath
    encryption_key: str
    bootstrap_username: str
    bootstrap_password_file: Path
    cookie_secure: bool
    allowed_origin: str | None
    base_path: str = ""

    @classmethod
    def from_env(cls) -> Settings:
        data_root = Path(os.getenv("PANEL_DATA_ROOT", "./data")).resolve()
        host_data_root = PurePosixPath(
            os.getenv("PANEL_HOST_DATA_ROOT", str(data_root).replace("\\", "/"))
        )
        configured_base_path = os.getenv("PANEL_BASE_PATH", "").strip()
        trimmed_base_path = configured_base_path.strip("/")
        base_path = f"/{trimmed_base_path}" if trimmed_base_path else ""
        encryption_key = os.getenv("PANEL_ENCRYPTION_KEY", "")
        if not encryption_key:
            raise RuntimeError("PANEL_ENCRYPTION_KEY is required")
        Fernet(encryption_key.encode("ascii"))

        return cls(
            data_root=data_root,
            host_data_root=host_data_root,
            encryption_key=encryption_key,
            bootstrap_username=os.getenv("PANEL_BOOTSTRAP_USERNAME", "admin"),
            bootstrap_password_file=Path(
                os.getenv(
                    "PANEL_BOOTSTRAP_PASSWORD_FILE",
                    str(data_root / "secrets" / "bootstrap_admin_password"),
                )
            ),
            cookie_secure=os.getenv("PANEL_COOKIE_SECURE", "false").lower() == "true",
            allowed_origin=os.getenv("PANEL_ALLOWED_ORIGIN") or None,
            base_path=base_path,
        )
