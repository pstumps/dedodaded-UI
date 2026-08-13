import io
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import httpx

from dedodaded.mods import (
    SteamWorkshopClient,
    ThunderstoreClient,
    ThunderstorePackage,
    ValheimModInstaller,
)

CATALOG = [
    {
        "owner": "Author",
        "name": "Clock",
        "full_name": "Author-Clock",
        "versions": [
            {
                "version_number": "2.0.0",
                "description": "A useful clock",
                "download_url": "https://gcdn.thunderstore.io/clock.zip",
                "dependencies": ["Author-Library-1.2.0", "denikson-BepInExPack_Valheim-5.4.0"],
                "downloads": 50,
            }
        ],
    },
    {
        "owner": "Author",
        "name": "Library",
        "full_name": "Author-Library",
        "versions": [
            {
                "version_number": "1.2.0",
                "description": "Shared library",
                "download_url": "https://gcdn.thunderstore.io/library.zip",
                "dependencies": [],
                "downloads": 100,
            }
        ],
    },
]


def catalog_transport(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=CATALOG, request=request)


def plugin_archive(*names: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name in names:
            archive.writestr(name, b"plugin")
    return output.getvalue()


class ThunderstoreClientTests(TestCase):
    def test_search_and_dependency_resolution_use_catalog_shape(self) -> None:
        client = ThunderstoreClient(
            httpx.Client(transport=httpx.MockTransport(catalog_transport))
        )

        results = client.search("clock")
        resolved = client.resolve_with_dependencies("Author-Clock")

        self.assertEqual(results[0].version, "2.0.0")
        self.assertEqual(
            [package.package_id for package in resolved],
            ["Author-Library", "Author-Clock"],
        )


class SteamWorkshopClientTests(TestCase):
    def test_looks_up_public_workshop_metadata(self) -> None:
        def transport(request: httpx.Request) -> httpx.Response:
            self.assertIn(b"publishedfileids%5B0%5D=2169435993", request.content)
            return httpx.Response(
                200,
                json={
                    "response": {
                        "publishedfiledetails": [
                            {
                                "result": 1,
                                "title": "Mod Options",
                                "description": "Shared settings UI",
                                "preview_url": "https://steamusercontent.example/preview.jpg",
                            }
                        ]
                    }
                },
                request=request,
            )

        client = SteamWorkshopClient(
            httpx.Client(transport=httpx.MockTransport(transport))
        )

        item = client.lookup("2169435993")

        self.assertEqual(item.title, "Mod Options")

    def test_rejects_non_numeric_workshop_id_without_network_call(self) -> None:
        client = SteamWorkshopClient()

        with self.assertRaisesRegex(ValueError, "only digits"):
            client.lookup("not-an-id")


class ValheimModInstallerTests(TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def test_installs_only_plugin_payload_under_managed_directory(self) -> None:
        archive = plugin_archive(
            "manifest.json",
            "BepInEx/plugins/Clock/Clock.dll",
            "BepInEx/config/Clock.cfg",
        )

        def transport(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=archive, request=request)

        installer = ValheimModInstaller(
            self.root,
            httpx.Client(transport=httpx.MockTransport(transport)),
        )
        package = ThunderstorePackage(
            "Author-Clock",
            "Clock",
            "Author",
            "A clock",
            "2.0.0",
            "https://gcdn.thunderstore.io/clock.zip",
            (),
            50,
            None,
            None,
        )

        target = installer.install("mistlands", package)

        self.assertEqual((target / "Clock/Clock.dll").read_bytes(), b"plugin")
        self.assertFalse((target / "Clock.cfg").exists())

    def test_rejects_path_traversal(self) -> None:
        archive = plugin_archive("BepInEx/plugins/../../escape.dll")

        def transport(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=archive, request=request)

        installer = ValheimModInstaller(
            self.root,
            httpx.Client(transport=httpx.MockTransport(transport)),
        )
        package = ThunderstorePackage(
            "Author-Bad",
            "Bad",
            "Author",
            "Bad archive",
            "1.0.0",
            "https://gcdn.thunderstore.io/bad.zip",
            (),
            0,
            None,
            None,
        )

        with self.assertRaisesRegex(ValueError, "unsafe path"):
            installer.install("mistlands", package)
        self.assertFalse((self.root / "escape.dll").exists())

    def test_rejects_non_thunderstore_download_url(self) -> None:
        installer = ValheimModInstaller(self.root)
        package = ThunderstorePackage(
            "Author-Bad",
            "Bad",
            "Author",
            "Bad URL",
            "1.0.0",
            "https://example.com/bad.zip",
            (),
            0,
            None,
            None,
        )

        with self.assertRaisesRegex(ValueError, "must come from Thunderstore"):
            installer.install("mistlands", package)
