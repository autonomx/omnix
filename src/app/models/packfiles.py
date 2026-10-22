"""Runtime pack file lists: the exact wheel each locked requirement installs on a platform (roadmap §4.3).

A runtime pack is a hash-locked requirement file. At release time this module
resolves each requirement to one wheel compatible with the pack's platform
(CPython 3.11): its URL on PyPI or download.pytorch.org, its SHA-256 (which
must be one of the lock's hashes) and its size. The result,
``requirements/desktop/packs/<runtime>.json``, ships inside the installer; the
app downloads exactly those files and refuses any whose digest differs. Nothing
is resolved against a package index on the user's machine.

A few locked packages publish only a source archive. Those are built into
wheels at release time (``scripts/desktop_locks.py wheelhouse``), committed
under ``requirements/desktop/wheelhouse`` and shipped in the installer, so no
user machine ever builds a package or fetches an unhashed build dependency.
"""
from __future__ import annotations

import hashlib
import html.parser
import json
import urllib.parse
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.models.locks import Lock, LockedRequirement, normalize

PYTHON_VERSION = (3, 11)
# MLX and onnxruntime publish macOS 13+ wheels; the desktop app supports macOS 14 (Sonoma) and later.
MACOS_MINIMUM = (14, 0)
PYPI_JSON = "https://pypi.org/pypi/{name}/{version}/json"
PYTORCH_INDEX = "https://download.pytorch.org/whl/{label}/{name}/"
PACK_FILES_VERSION = 1
# Where pack wheels may come from: PyPI's file host and PyTorch's index (which serves files from its R2 bucket).
ALLOWED_URL_PREFIXES = ("https://files.pythonhosted.org/", "https://download.pytorch.org/",
                        "https://download-r2.pytorch.org/")


class PackFilesError(ValueError):
    pass


@dataclass(frozen=True)
class PackFile:
    name: str
    version: str
    filename: str
    sha256: str
    size: int | None
    # "index": downloaded from url; "bundled": shipped in the installer's wheelhouse.
    source: str
    url: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def platform_tags(platform: str) -> list[Any]:
    """Wheel tags CPython 3.11 accepts on ``platform``, most specific first."""
    from packaging import tags

    if platform == "windows-x64":
        platforms = ["win_amd64"]
    elif platform == "macos-arm64":
        platforms = list(tags.mac_platforms(MACOS_MINIMUM, "arm64"))
    elif platform == "macos-x64":
        platforms = list(tags.mac_platforms(MACOS_MINIMUM, "x86_64"))
    elif platform == "linux-x64":
        platforms = [f"manylinux_2_{minor}_x86_64" for minor in range(28, 16, -1)] + [
            "manylinux2014_x86_64", "linux_x86_64"]
    else:
        raise PackFilesError(f"unknown platform {platform!r}")
    ordered = list(tags.cpython_tags(PYTHON_VERSION, platforms=platforms))
    ordered += list(tags.compatible_tags(PYTHON_VERSION, interpreter="cp311", platforms=platforms))
    return ordered


def _wheel_rank(filename: str, ranked: dict[Any, int]) -> int | None:
    from packaging.utils import InvalidWheelFilename, parse_wheel_filename

    try:
        _, _, _, wheel_tags = parse_wheel_filename(filename)
    except InvalidWheelFilename:
        return None
    ranks = [ranked[tag] for tag in wheel_tags if tag in ranked]
    return min(ranks) if ranks else None


class _Links(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


Fetch = Callable[[str], bytes]


def _http_get(url: str) -> bytes:
    import urllib.request

    request = urllib.request.Request(url, headers={"User-Agent": "omnix-desktop-locks"})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed https hosts
        return response.read()


def _http_size(url: str) -> int | None:
    import urllib.request

    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "omnix-desktop-locks"})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed https hosts
        length = response.headers.get("Content-Length")
    return int(length) if length else None


def _candidates(item: LockedRequirement, fetch: Fetch) -> list[dict[str, Any]]:
    """Every file published for the requirement: filename, url, sha256, size."""
    if "+" in item.version:
        label = item.version.split("+", 1)[1]
        index = PYTORCH_INDEX.format(label=label, name=normalize(item.name))
        parser = _Links()
        parser.feed(fetch(index).decode("utf-8", errors="replace"))
        found = []
        for href in parser.links:
            url, _, fragment = urllib.parse.urljoin(index, href).partition("#")
            digest = fragment.removeprefix("sha256=") if fragment.startswith("sha256=") else ""
            filename = urllib.parse.unquote(url.rsplit("/", 1)[-1])
            found.append({"filename": filename, "url": url, "sha256": digest, "size": None})
        return found
    payload = json.loads(fetch(PYPI_JSON.format(name=normalize(item.name), version=item.version)))
    return [{"filename": entry["filename"], "url": entry["url"], "sha256": entry["digests"]["sha256"],
             "size": int(entry["size"])} for entry in payload.get("urls", [])]


def _bundled(item: LockedRequirement, wheelhouse: Path, ranked: dict[Any, int]) -> PackFile | None:
    from packaging.utils import parse_wheel_filename

    for wheel in sorted(wheelhouse.glob("*.whl")):
        name, version, _, _ = parse_wheel_filename(wheel.name)
        if normalize(str(name)) == item.key and str(version) == item.version and _wheel_rank(wheel.name, ranked) is not None:
            return PackFile(item.name, item.version, wheel.name, _sha256(wheel), wheel.stat().st_size, "bundled")
    return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve(lock: Lock, platform: str, *, wheelhouse: Path, fetch: Fetch = _http_get,
            size_of: Callable[[str], int | None] = _http_size) -> tuple[list[PackFile], list[str]]:
    """(files, source-only requirements with no bundled wheel yet)."""
    ranked = {tag: index for index, tag in enumerate(platform_tags(platform))}
    files: list[PackFile] = []
    needs_wheel: list[str] = []
    for item in lock.requirements:
        best: tuple[int, dict[str, Any]] | None = None
        for candidate in _candidates(item, fetch):
            if candidate["sha256"] not in item.hashes or not candidate["filename"].endswith(".whl"):
                continue
            rank = _wheel_rank(candidate["filename"], ranked)
            if rank is not None and (best is None or rank < best[0]):
                best = (rank, candidate)
        if best is not None:
            chosen = best[1]
            # The PyTorch index lists no sizes; the setup screen shows them, so ask the server.
            size = chosen["size"] if chosen["size"] is not None else size_of(chosen["url"])
            files.append(PackFile(item.name, item.version, chosen["filename"], chosen["sha256"], size,
                                  "index", chosen["url"]))
            continue
        bundled = _bundled(item, wheelhouse, ranked)
        if bundled is not None:
            files.append(bundled)
        else:
            needs_wheel.append(f"{item.name}=={item.version}")
    return files, needs_wheel


def sdist_for(item: LockedRequirement, fetch: Fetch = _http_get) -> dict[str, Any] | None:
    """The requirement's source archive whose digest the lock allows (for building a wheelhouse wheel)."""
    for candidate in _candidates(item, fetch):
        if candidate["sha256"] in item.hashes and candidate["filename"].endswith((".tar.gz", ".zip")):
            return candidate
    return None


def write_pack_files(path: Path, runtime_id: str, platform: str, lock_path: str, lock_text: str,
                     files: Iterable[PackFile]) -> None:
    payload = {
        "pack_files_version": PACK_FILES_VERSION,
        "runtime": runtime_id,
        "platform": platform,
        "lock": lock_path,
        "lock_sha256": hashlib.sha256(lock_text.encode("utf-8")).hexdigest(),
        "files": [item.as_dict() for item in files],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class PackFiles:
    runtime: str
    platform: str
    lock: str
    lock_sha256: str
    files: tuple[PackFile, ...]

    @property
    def download_bytes(self) -> int:
        return sum(item.size or 0 for item in self.files if item.source == "index")


def load_pack_files(path: Path) -> PackFiles:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("pack_files_version") != PACK_FILES_VERSION:
        raise PackFilesError(f"{path.name}: unsupported pack_files_version")
    files = []
    for entry in raw["files"]:
        item = PackFile(**entry)
        if item.source not in {"index", "bundled"} or len(item.sha256) != 64:
            raise PackFilesError(f"{path.name}: {item.filename} has no source or digest")
        if item.source == "index" and not item.url.startswith(ALLOWED_URL_PREFIXES):
            raise PackFilesError(f"{path.name}: {item.filename} is not from PyPI or download.pytorch.org")
        files.append(item)
    return PackFiles(str(raw["runtime"]), str(raw["platform"]), str(raw["lock"]), str(raw["lock_sha256"]),
                     tuple(files))


def check_pack_files(pack: PackFiles, lock: Lock, lock_text: str, *, wheelhouse: Path) -> list[str]:
    """Problems: one file per locked requirement, each with a digest the lock (or the shipped wheelhouse) vouches for."""
    problems = []
    if pack.lock_sha256 != hashlib.sha256(lock_text.encode("utf-8")).hexdigest():
        problems.append(f"{pack.runtime}: the file list was made from another version of {pack.lock}")
    by_key: dict[str, list[PackFile]] = {}
    for item in pack.files:
        by_key.setdefault(normalize(item.name), []).append(item)
    for requirement in lock.requirements:
        listed = by_key.pop(requirement.key, [])
        if len(listed) != 1:
            problems.append(f"{pack.runtime}: {requirement.name} has {len(listed)} files, expected 1")
            continue
        item = listed[0]
        if item.version != requirement.version:
            problems.append(f"{pack.runtime}: {item.filename} is not version {requirement.version}")
        if item.source == "index" and item.sha256 not in requirement.hashes:
            problems.append(f"{pack.runtime}: {item.filename}'s digest is not in the lock")
        if item.source == "bundled":
            wheel = wheelhouse / item.filename
            if not wheel.is_file() or _sha256(wheel) != item.sha256:
                problems.append(f"{pack.runtime}: the bundled {item.filename} is missing or changed")
    for key in sorted(by_key):
        problems.append(f"{pack.runtime}: {key} is listed but not locked")
    return problems


__all__ = [
    "PackFile", "PackFiles", "PackFilesError", "check_pack_files", "load_pack_files", "platform_tags", "resolve",
    "sdist_for", "write_pack_files",
]
