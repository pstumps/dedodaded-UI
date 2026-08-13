from __future__ import annotations

import os

import uvicorn

from deddodaded.api import create_panel_app
from deddodaded.settings import Settings


def create_application():  # type: ignore[no-untyped-def]
    return create_panel_app(Settings.from_env())


def run() -> None:
    uvicorn.run(
        "deddodaded.main:create_application",
        factory=True,
        host=os.getenv("PANEL_BIND_HOST", "0.0.0.0"),
        port=int(os.getenv("PANEL_PORT", "8080")),
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("PANEL_FORWARDED_ALLOW_IPS", "127.0.0.1"),
    )


if __name__ == "__main__":
    run()
