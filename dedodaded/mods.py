from __future__ import annotations

import hashlib
import io
import re
import shutil
import stat
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

import httpx

from dedodaded.game_specs import ModReference

THUNDERSTORE_API = "https://thunderstore.io/c/valheim/api/v1/package/"
STEAM_WORKSHOP_API = (
    "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
)
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
MAX_EXTRACTED_BYTES = 500 * 1024 * 1024
MAX_ARCHIVE_FILES = 10_000
DEPENDENCY_PATTERN = re.compile(r"^(.+)-(\d+\.\d+\.\d+)$")


@dataclass(frozen=True, slots=True)
class ThunderstorePackage:
    package_id: str
    name: str
    owner: str
    description: str
    version: str
    download_url: str
    dependencies: tuple[str, ...]
    downloads: int
    icon_url: str | None
    website_url: str | None

    def as_mod_reference(self) -> ModReference:
        return ModReference(
            source_id=self.package_id,
            name=self.name,
            download_url=self.download_url,
            version=self.version,
        )


@dataclass(frozen=True, slots=True)
class WorkshopItem:
    workshop_id: str
    title: str
    description: str
    preview_url: str | None


class SteamWorkshopClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(
            timeout=15,
            follow_redirects=True,
            headers={"User-Agent": "Dedodaded/0.1 (+self-hosted-server-panel)"},
        )

    def lookup(self, workshop_id: str) -> WorkshopItem:
        if not workshop_id.isascii() or not workshop_id.isdigit():
            raise ValueError("A Steam Workshop ID must contain only digits")
        response = self.client.post(
            STEAM_WORKSHOP_API,
            data={"itemcount": "1", "publishedfileids[0]": workshop_id},
        )
        response.raise_for_status()
        payload = response.json()
        details = payload.get("response", {}).get("publishedfiledetails", [])
        if not details or int(details[0].get("result", 0)) != 1:
            raise LookupError(f"Steam Workshop item {workshop_id!r} was not found")
        item = details[0]
        return WorkshopItem(
            workshop_id=workshop_id,
            title=str(item.get("title") or f"Workshop item {workshop_id}"),
            description=str(item.get("description") or ""),
            preview_url=str(item["preview_url"]) if item.get("preview_url") else None,
        )


class ThunderstoreClient:
    def __init__(
        self,
        client: httpx.Client | None = None,
        cache_seconds: int = 600,
    ) -> None:
        self.client = client or httpx.Client(
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "Dedodaded/0.1 (+self-hosted-server-panel)"},
        )
        self.cache_seconds = cache_seconds
        self._cached_at = 0.0
        self._raw_packages: list[dict[str, Any]] = []

    def search(self, query: str, limit: int = 30) -> list[ThunderstorePackage]:
        normalized_query = query.casefold().strip()
        matches: list[tuple[int, ThunderstorePackage]] = []
        for raw_package in self._packages():
            package = self._to_package(raw_package)
            searchable = " ".join(
                (package.package_id, package.name, package.owner, package.description)
            ).casefold()
            if normalized_query and normalized_query not in searchable:
                continue
            score = package.downloads
            if normalized_query and package.name.casefold().startswith(normalized_query):
                score += 10**12
            matches.append((score, package))
        matches.sort(key=lambda match: match[0], reverse=True)
        return [package for _, package in matches[: max(1, min(limit, 50))]]

    def resolve_with_dependencies(self, package_id: str) -> list[ThunderstorePackage]:
        raw_by_id = {self._package_id(package): package for package in self._packages()}
        resolved: list[ThunderstorePackage] = []
        visited: set[tuple[str, str | None]] = set()

        def visit(current_id: str, version: str | None = None) -> None:
            key = (current_id.casefold(), version)
            if key in visited or current_id.casefold() == "denikson-bepinexpack_valheim":
                return
            visited.add(key)
            raw = raw_by_id.get(current_id)
            if raw is None:
                raise LookupError(f"Thunderstore package {current_id!r} was not found")
            package = self._to_package(raw, version)
            for dependency in package.dependencies:
                match = DEPENDENCY_PATTERN.fullmatch(dependency)
                dependency_id = match.group(1) if match else dependency
                dependency_version = match.group(2) if match else None
                visit(dependency_id, dependency_version)
            resolved.append(package)

        visit(package_id)
        return resolved

    def _packages(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        if self._raw_packages and now - self._cached_at < self.cache_seconds:
            return self._raw_packages
        response = self.client.get(THUNDERSTORE_API)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Thunderstore returned an invalid package catalog")
        self._raw_packages = [package for package in payload if isinstance(package, dict)]
        self._cached_at = now
        return self._raw_packages

    def _to_package(
        self, raw_package: dict[str, Any], requested_version: str | None = None
    ) -> ThunderstorePackage:
        versions = raw_package.get("versions")
        if not isinstance(versions, list) or not versions:
            raise ValueError(f"Package {self._package_id(raw_package)!r} has no versions")
        raw_version = next(
            (
                version
                for version in versions
                if isinstance(version, dict)
                and (
                    requested_version is None
                    or str(version.get("version_number")) == requested_version
                )
            ),
            None,
        )
        if raw_version is None:
            raise LookupError(
                f"Package {self._package_id(raw_package)!r} does not have version "
                f"{requested_version!r}"
            )
        dependencies = raw_version.get("dependencies") or []
        return ThunderstorePackage(
            package_id=self._package_id(raw_package),
            name=str(raw_package.get("name") or "Unknown package"),
            owner=str(raw_package.get("owner") or "Unknown owner"),
            description=str(raw_version.get("description") or ""),
            version=str(raw_version.get("version_number") or "unknown"),
            download_url=str(raw_version.get("download_url") or ""),
            dependencies=tuple(str(dependency) for dependency in dependencies),
            downloads=int(raw_version.get("downloads") or 0),
            icon_url=str(raw_version["icon"]) if raw_version.get("icon") else None,
            website_url=(
                str(raw_version["website_url"]) if raw_version.get("website_url") else None
            ),
        )

    @staticmethod
    def _package_id(raw_package: dict[str, Any]) -> str:
        full_name = raw_package.get("full_name")
        if full_name:
            return str(full_name)
        return f"{raw_package.get('owner', '')}-{raw_package.get('name', '')}"


class ValheimModInstaller:
    def __init__(self, data_root: Path, client: httpx.Client | None = None) -> None:
        self.data_root = data_root
        self.client = client or httpx.Client(
            timeout=60,
            follow_redirects=True,
            headers={"User-Agent": "Dedodaded/0.1 (+self-hosted-server-panel)"},
        )

    def install(self, instance_id: str, package: ThunderstorePackage) -> Path:
        self._validate_download_url(package.download_url)
        with self.client.stream("GET", package.download_url) as response:
            response.raise_for_status()
            self._validate_download_url(str(response.url))
            declared_size = int(response.headers.get("content-length", "0"))
            if declared_size > MAX_DOWNLOAD_BYTES:
                raise ValueError("The mod archive is larger than 100 MB")
            archive_bytes = bytearray()
            for chunk in response.iter_bytes():
                archive_bytes.extend(chunk)
                if len(archive_bytes) > MAX_DOWNLOAD_BYTES:
                    raise ValueError("The mod archive is larger than 100 MB")

        plugins_root = (
            self.data_root / "instances" / instance_id / "config" / "bepinex" / "plugins"
        )
        plugins_root.mkdir(parents=True, exist_ok=True)
        target = plugins_root / self._folder_name(package.package_id)
        temporary = Path(tempfile.mkdtemp(prefix=".install-", dir=plugins_root))
        try:
            self._extract_plugins(bytes(archive_bytes), temporary)
            if target.exists():
                shutil.rmtree(target)
            temporary.replace(target)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        return target

    def uninstall(self, instance_id: str, package_id: str) -> None:
        target = (
            self.data_root
            / "instances"
            / instance_id
            / "config"
            / "bepinex"
            / "plugins"
            / self._folder_name(package_id)
        )
        shutil.rmtree(target, ignore_errors=True)

    @staticmethod
    def _extract_plugins(archive_bytes: bytes, destination: Path) -> None:
        try:
            archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
        except zipfile.BadZipFile as error:
            raise ValueError("Thunderstore returned an invalid ZIP archive") from error
        with archive:
            files = [member for member in archive.infolist() if not member.is_dir()]
            if len(files) > MAX_ARCHIVE_FILES:
                raise ValueError("The mod archive contains too many files")
            if sum(member.file_size for member in files) > MAX_EXTRACTED_BYTES:
                raise ValueError("The extracted mod would be larger than 500 MB")

            extracted_dll = False
            for member in files:
                if stat.S_ISLNK(member.external_attr >> 16):
                    raise ValueError("Symbolic links are not allowed in mod archives")
                relative_path = ValheimModInstaller._plugin_relative_path(member.filename)
                if relative_path is None:
                    continue
                target = destination.joinpath(*relative_path.parts)
                if destination.resolve() not in target.resolve().parents:
                    raise ValueError("The mod archive contains an unsafe path")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                extracted_dll = extracted_dll or target.suffix.casefold() == ".dll"
            if not extracted_dll:
                raise ValueError("The package does not contain a BepInEx plugin DLL")

    @staticmethod
    def _plugin_relative_path(filename: str) -> PurePosixPath | None:
        path = PurePosixPath(filename.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("The mod archive contains an unsafe path")
        lowered = tuple(part.casefold() for part in path.parts)
        if len(lowered) >= 3 and lowered[:2] == ("bepinex", "plugins"):
            return PurePosixPath(*path.parts[2:])
        if len(lowered) >= 2 and lowered[0] == "plugins":
            return PurePosixPath(*path.parts[1:])
        if lowered and lowered[0] == "bepinex":
            return None
        if len(path.parts) == 1 and path.name.casefold() in {
            "manifest.json",
            "icon.png",
            "readme.md",
            "changelog.md",
            "license",
        }:
            return None
        return path

    @staticmethod
    def _validate_download_url(url: str) -> None:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").casefold()
        if parsed.scheme != "https" or not (
            hostname == "thunderstore.io" or hostname.endswith(".thunderstore.io")
        ):
            raise ValueError("Mod downloads must come from Thunderstore over HTTPS")

    @staticmethod
    def _folder_name(package_id: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", package_id).strip("-.")[:60]
        digest = hashlib.sha256(package_id.encode()).hexdigest()[:8]
        return f"{slug or 'mod'}-{digest}"
