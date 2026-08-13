from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import PurePosixPath


class Game(StrEnum):
    PROJECT_ZOMBOID = "project-zomboid"
    VALHEIM = "valheim"


@dataclass(frozen=True, slots=True)
class ModReference:
    source_id: str
    name: str
    mod_id: str | None = None
    download_url: str | None = None
    version: str | None = None


@dataclass(frozen=True, slots=True)
class ServerConfig:
    instance_id: str
    game: Game
    name: str
    world_name: str
    password: str
    admin_password: str
    port: int
    max_players: int
    public: bool = True
    mods: tuple[ModReference, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ContainerSpec:
    image: str
    environment: dict[str, str]
    ports: dict[str, int]
    volumes: dict[str, dict[str, str]]
    stop_timeout: int = 120
    cap_add: tuple[str, ...] = ()


def build_container_spec(
    config: ServerConfig, host_data_root: str | PurePosixPath
) -> ContainerSpec:
    host_data_root = PurePosixPath(host_data_root)
    if not 1024 <= config.port <= 65533:
        raise ValueError("The base port must be between 1024 and 65533")
    if config.game is Game.VALHEIM:
        return _build_valheim_spec(config, host_data_root)
    return _build_zomboid_spec(config, host_data_root)


def _build_valheim_spec(
    config: ServerConfig, host_data_root: PurePosixPath
) -> ContainerSpec:
    if len(config.password) < 5:
        raise ValueError("Valheim server passwords must contain at least 5 characters")

    instance_root = host_data_root / "instances" / config.instance_id
    environment = {
        "SERVER_NAME": config.name,
        "WORLD_NAME": config.world_name,
        "SERVER_PASS": config.password,
        "SERVER_PUBLIC": str(config.public).lower(),
        "SERVER_PORT": str(config.port),
        "BACKUPS": "true",
        "UPDATE_IF_IDLE": "true",
        "TZ": "Etc/UTC",
    }
    if config.mods:
        environment["BEPINEX"] = "true"

    return ContainerSpec(
        image="ghcr.io/community-valheim-tools/valheim-server:latest",
        environment=environment,
        ports={
            f"{config.port}/udp": config.port,
            f"{config.port + 1}/udp": config.port + 1,
            f"{config.port + 2}/udp": config.port + 2,
        },
        volumes={
            str(instance_root / "config"): {"bind": "/config", "mode": "rw"},
            str(instance_root / "server"): {"bind": "/opt/valheim", "mode": "rw"},
        },
        cap_add=("SYS_NICE",),
    )


def _build_zomboid_spec(
    config: ServerConfig, host_data_root: PurePosixPath
) -> ContainerSpec:
    instance_root = host_data_root / "instances" / config.instance_id
    environment = {
        "SERVER_NAME": config.name,
        "SERVER_PASSWORD": config.password,
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD": config.admin_password,
        "DEFAULT_PORT": str(config.port),
        "UDP_PORT": str(config.port + 1),
        "MAX_PLAYERS": str(config.max_players),
        "PUBLIC_SERVER": str(config.public).lower(),
        "PAUSE_ON_EMPTY": "true",
        "MAX_RAM": "4096m",
        "TZ": "Etc/UTC",
    }
    if config.mods:
        if any(not mod.mod_id for mod in config.mods):
            raise ValueError("Project Zomboid mods require both a Workshop ID and mod ID")
        environment["MOD_WORKSHOP_IDS"] = ";".join(mod.source_id for mod in config.mods)
        environment["MOD_NAMES"] = ";".join(mod.mod_id or "" for mod in config.mods)

    return ContainerSpec(
        image="ghcr.io/renegade-master/zomboid-dedicated-server:latest",
        environment=environment,
        ports={
            f"{config.port}/udp": config.port,
            f"{config.port + 1}/udp": config.port + 1,
        },
        volumes={
            str(instance_root / "config"): {"bind": "/home/steam/Zomboid", "mode": "rw"},
            str(instance_root / "server"): {
                "bind": "/home/steam/ZomboidDedicatedServer",
                "mode": "rw",
            },
        },
    )
