"""The community world catalog: worlds people share as GitHub release files, listed in one public index.

The catalog is a public GitHub repository (``autonomx/omnix-worlds`` unless ``OMNIX_RPG_WORLD_CATALOG_REPO`` names
another). Its ``index.json`` lists each world with the release file that holds its bundle, that file's size and its
SHA-256. Installing downloads the file from that repository's releases only, checks its size and digest against the
index, and imports it like any other bundle; the world then waits for someone here to adopt it
(:mod:`.world_adoption`) before it can be played.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import ssl
import urllib.error
import urllib.request
from typing import Any, Callable

import certifi
from pydantic import BaseModel, ConfigDict, Field

from app.config.env import env_str
from app.persistence.unit_of_work import unit_of_work
from app.runtime.paths import resources_data_root
from app.runtime.tenant_context import current_tenant

from .world_adoption import shared_world_state
from .world_bundle import MAX_WORLD_BUNDLE_BYTES
from .world_bundle_import import WorldBundleImportConflict, import_world_bundle

CATALOG_SCHEMA = "omnix-world-catalog-v1"
DEFAULT_CATALOG_REPO = "autonomx/omnix-worlds"
MAX_CATALOG_INDEX_BYTES = 4 * 1024 * 1024
MAX_CATALOG_COVER_BYTES = 8 * 1024 * 1024
_REPO_RE = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

Download = Callable[[str, int], bytes]


class CatalogFile(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    url: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(ge=1)


class CatalogWorld(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")
    version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=2000)
    genre: str = Field(default="", max_length=120)
    tone: str = Field(default="", max_length=200)
    author: str = Field(min_length=1, max_length=100)
    published_at: str = ""
    bundle: CatalogFile
    cover: CatalogFile | None = None


class CatalogIndex(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    schema_version: str
    updated_at: str = ""
    worlds: tuple[CatalogWorld, ...] = ()


def catalog_repo() -> str:
    repo = (env_str("OMNIX_RPG_WORLD_CATALOG_REPO") or DEFAULT_CATALOG_REPO).strip()
    if not _REPO_RE.fullmatch(repo):
        raise ValueError(f"world_catalog_repo_invalid:{repo}")
    return repo


def _download(url: str, limit: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Omnix-World-Catalog/1.0"})
    with urllib.request.urlopen(request, timeout=60, context=_SSL_CONTEXT) as response:
        if int(response.headers.get("Content-Length") or 0) > limit:
            raise ValueError("world_catalog_download_too_large")
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("world_catalog_download_too_large")
    return data


def _release_file_url(repo: str, url: str) -> str:
    # Only this catalog's own release files: an index entry cannot point Omnix at another host or repository.
    if not url.startswith(f"https://github.com/{repo}/releases/download/") or ".." in url:
        raise ValueError("world_catalog_file_url_untrusted")
    return url


def _verified(content: bytes, expected: CatalogFile) -> bytes:
    if len(content) != expected.bytes or not hmac.compare_digest(hashlib.sha256(content).hexdigest(), expected.sha256):
        raise ValueError("world_catalog_file_digest_mismatch")
    return content


def load_catalog(*, download: Download = _download) -> CatalogIndex:
    repo = catalog_repo()
    try:
        raw = download(f"https://raw.githubusercontent.com/{repo}/main/index.json", MAX_CATALOG_INDEX_BYTES)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return CatalogIndex(schema_version=CATALOG_SCHEMA)
        raise ValueError(f"world_catalog_unavailable:{exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ValueError("world_catalog_unreachable") from exc
    index = CatalogIndex.model_validate(json.loads(raw.decode("utf-8")))
    if index.schema_version != CATALOG_SCHEMA:
        raise ValueError(f"world_catalog_schema_unsupported:{index.schema_version}")
    return index


def _installed(database: Any | None) -> dict[str, dict[str, Any]]:
    """Worlds here that came from the catalog, by catalog id: the newest version installed wins."""
    context = current_tenant()
    with unit_of_work(database) as work:
        worlds = work.world_scenarios.list_worlds(context, limit=500)
        work.rollback()
    found: dict[str, dict[str, Any]] = {}
    for world in worlds:
        state = shared_world_state(world)
        entry_id = str(state["catalog"].get("id") or "")
        if not entry_id:
            continue
        version = int(state["catalog"].get("version") or 0)
        if version >= int(found.get(entry_id, {}).get("version") or 0):
            found[entry_id] = {
                "world_id": str(world["id"]),
                "version": version,
                "bundle_sha256": state["bundle_sha256"],
                "adopted": state["adopted"],
            }
    return found


def list_catalog(*, database: Any | None = None, download: Download = _download) -> dict[str, Any]:
    index = load_catalog(download=download)
    installed = _installed(database)
    return {
        "ok": True,
        "repo": catalog_repo(),
        "updated_at": index.updated_at,
        "worlds": [
            {
                **entry.model_dump(mode="json", exclude={"cover"}),
                "has_cover": entry.cover is not None,
                "installed": installed.get(entry.id),
            }
            for entry in index.worlds
        ],
    }


def _entry(index: CatalogIndex, entry_id: str) -> CatalogWorld:
    entry = next((item for item in index.worlds if item.id == entry_id), None)
    if entry is None:
        raise KeyError(f"world_catalog_entry_not_found:{entry_id}")
    return entry


def import_catalog_world(
    entry_id: str,
    *,
    database: Any | None = None,
    download: Download = _download,
) -> dict[str, Any]:
    """Download a catalog world's bundle, check it against the index, and import it (not yet adopted)."""

    repo = catalog_repo()
    entry = _entry(load_catalog(download=download), entry_id)
    if entry.bundle.bytes > MAX_WORLD_BUNDLE_BYTES:
        raise ValueError("world_bundle_size_limit_exceeded")
    existing = _installed(database).get(entry.id)
    if existing and existing["bundle_sha256"] == entry.bundle.sha256:
        return {"ok": True, "status": "installed", "reused": True, **existing}
    content = _verified(download(_release_file_url(repo, entry.bundle.url), entry.bundle.bytes), entry.bundle)
    catalog = {"repo": repo, "id": entry.id, "version": entry.version, "author": entry.author, "title": entry.title}
    target = f"world:{entry.id}"
    for attempt in range(1, 21):
        candidate = target if attempt == 1 else f"{target}-{attempt}"
        try:
            imported = import_world_bundle(content, target_world_id=candidate, catalog=catalog, database=database)
        except WorldBundleImportConflict:
            continue
        return {
            "ok": True,
            "status": "installed",
            "reused": False,
            "world_id": imported["world_id"],
            "version": entry.version,
            "bundle_sha256": imported["bundle_sha256"],
            "adopted": False,
        }
    raise ValueError(f"world_catalog_install_no_free_id:{entry.id}")


def catalog_cover(entry_id: str, *, download: Download = _download) -> tuple[bytes, str]:
    """A catalog world's cover image, kept by digest once checked."""

    repo = catalog_repo()
    entry = _entry(load_catalog(download=download), entry_id)
    if entry.cover is None:
        raise KeyError(f"world_catalog_cover_not_found:{entry_id}")
    if entry.cover.bytes > MAX_CATALOG_COVER_BYTES:
        raise ValueError("world_catalog_cover_too_large")
    cache = resources_data_root() / "rpg_world_catalog" / "covers" / entry.cover.sha256
    content = cache.read_bytes() if cache.is_file() else b""
    if not content:
        content = _verified(download(_release_file_url(repo, entry.cover.url), entry.cover.bytes), entry.cover)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(content)
    return _verified(content, entry.cover), _image_type(content)


def _image_type(content: bytes) -> str:
    if content.startswith(b"\x89PNG"):
        return "image/png"
    if content.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError("world_catalog_cover_type_unsupported")


__all__ = [
    "CATALOG_SCHEMA",
    "CatalogIndex",
    "CatalogWorld",
    "catalog_cover",
    "catalog_repo",
    "import_catalog_world",
    "list_catalog",
    "load_catalog",
]

