"""Runtime and model packs on disk, for the desktop app (desktop roadmap §4.3 and §4.9).

The desktop app sets ``OMNIX_PACKS_DIR``; this module is how Omnix installs,
checks and removes what the setup screen downloads under it::

    <packs>/runtimes/<runtime id>/   manifest.json, site/, scripts/, data/
    <packs>/models/                  the Hugging Face cache (HF_HUB_CACHE)
    <packs>/models/.omnix/<id>.json  when each model was installed, at which commit
    <packs>/staging/                 partial downloads and unpacked packs not yet in place

A runtime pack is downloaded wheel by wheel from the file list that ships in
the installer (``requirements/desktop/packs/<id>.json``); each download resumes
after an interruption and is checked against the listed SHA-256 before use.
The wheels are unpacked into staging and the folder is renamed into place, so a
pack is either complete or absent. A model pack is the catalog's pinned files,
fetched into the Hugging Face cache and checked against their digests.

Without ``OMNIX_PACKS_DIR`` (a developer checkout or the Docker deployment)
there are no packs: services run in their own environments and Voice Studio's
installer keeps its folders.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import shutil
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config.env import environment
from app.models import catalog as model_catalog
from app.models.catalog import Catalog, ModelEntry, RuntimePack
from app.models.packfiles import PackFile, PackFiles, load_pack_files
from app.models.wheels import install_wheel, verify_installed

logger = logging.getLogger(__name__)

MANIFEST = "manifest.json"
MANIFEST_VERSION = 1
# Unpacked wheels take more room than their downloads (Torch: 2.5 GB becomes about 5 GB).
UNPACK_FACTOR = 2.5
DISK_MARGIN_BYTES = 1 * 2**30
CHUNK_BYTES = 1024 * 1024

Progress = Callable[[int, int, str], None]
Cancelled = Callable[[], bool]


class PackError(RuntimeError):
    """A pack cannot be installed or removed as asked; the message says why."""


class PackCancelled(PackError):
    pass


def packs_root() -> Path | None:
    configured = environment().get("OMNIX_PACKS_DIR", "").strip()
    return Path(configured) if configured else None


def desktop_mode() -> bool:
    """Whether this Omnix manages runtime and model packs (the desktop app sets ``OMNIX_PACKS_DIR``)."""
    return packs_root() is not None


def wheelhouse() -> Path:
    from app.runtime.paths import repo_root

    return repo_root() / "requirements" / "desktop" / "wheelhouse"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _folder_bytes(folder: Path) -> int:
    total = 0
    for item in folder.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def _remove_tree(path: Path) -> None:
    """Deletes a folder this store owns. Links are unlinked, never followed (Git for Windows' lesson)."""
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        path.unlink()
        return
    shutil.rmtree(path)


def check_disk(folder: Path, needed: int) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(folder).free
    if free < needed + DISK_MARGIN_BYTES:
        raise PackError(f"not enough disk space: {needed / 1e9:.1f} GB needed, {free / 1e9:.1f} GB free on "
                        f"{folder.anchor or folder}")


@contextlib.contextmanager
def _pack_lock(path: Path, cancelled: Cancelled):
    """One install of a pack at a time, across jobs and processes; waiting honours cancellation."""
    from filelock import FileLock, Timeout

    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(path))
    while True:
        try:
            lock.acquire(timeout=2)
            break
        except Timeout:
            if cancelled():
                raise PackCancelled("cancelled") from None
    try:
        yield
    finally:
        lock.release()


# Downloads ----------------------------------------------------------------------------------------------------


def download_file(url: str, target: Path, *, sha256: str, size: int | None, progress: Callable[[int], None],
                  cancelled: Cancelled, client: Any = None) -> Path:
    """Fetch ``url`` to ``target``, resuming a ``.part`` file left by an interrupted run, and check its digest."""
    if target.is_file() and _sha256(target) == sha256:
        progress(target.stat().st_size)
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    if client is None:
        import httpx

        client = httpx.Client(follow_redirects=True, timeout=httpx.Timeout(60.0, read=300.0),
                              headers={"User-Agent": "omnix-desktop"})
    have = partial.stat().st_size if partial.exists() else 0
    if size is not None and have > size:
        partial.unlink()
        have = 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    with client.stream("GET", url, headers=headers) as response:
        if response.status_code == 416 and size is not None and have == size:
            pass  # the part file is already complete
        elif response.status_code == 206 and have:
            pass
        elif response.status_code == 200:
            have = 0  # the server ignored the range: start over
        else:
            raise PackError(f"download failed ({response.status_code}): {url}")
        if response.status_code != 416:
            mode = "ab" if have else "wb"
            progress(have)
            with partial.open(mode) as output:
                for chunk in response.iter_bytes(CHUNK_BYTES):
                    if cancelled():
                        raise PackCancelled("cancelled")
                    output.write(chunk)
                    progress(len(chunk))
    actual = _sha256(partial)
    if actual != sha256:
        partial.unlink(missing_ok=True)
        raise PackError(f"{target.name} has SHA-256 {actual}, expected {sha256}; it was deleted, try again")
    partial.replace(target)
    return target


# Runtime packs ------------------------------------------------------------------------------------------------


@dataclass
class RuntimeStore:
    root: Path
    catalog: Catalog

    @property
    def runtimes(self) -> Path:
        return self.root / "runtimes"

    @property
    def staging(self) -> Path:
        return self.root / "staging"

    def folder(self, runtime_id: str) -> Path:
        self.catalog.runtime(runtime_id)
        return self.runtimes / runtime_id

    def site(self, runtime_id: str) -> Path:
        return self.folder(runtime_id) / "site"

    def files(self, runtime_id: str) -> PackFiles:
        from app.runtime.paths import repo_root

        return load_pack_files(repo_root() / self.catalog.runtime(runtime_id).files)

    def manifest(self, runtime_id: str) -> dict[str, Any] | None:
        try:
            data = json.loads((self.folder(runtime_id) / MANIFEST).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def installed(self, runtime_id: str) -> bool:
        return self.manifest(runtime_id) is not None

    def current(self, runtime_id: str) -> bool:
        """Installed from the file list this build ships (an app update can change it)."""
        manifest = self.manifest(runtime_id)
        return manifest is not None and manifest.get("lock_sha256") == self.files(runtime_id).lock_sha256

    def download_bytes(self, runtime_id: str) -> int:
        return self.files(runtime_id).download_bytes

    def status(self, runtime_id: str) -> dict[str, Any]:
        pack = self.catalog.runtime(runtime_id)
        manifest = self.manifest(runtime_id)
        return {
            "id": pack.id, "label": pack.label, "kind": pack.kind, "platform": pack.platform,
            "accelerator": pack.accelerator, "base": pack.base, "licences": list(pack.licences),
            "requires": dict(pack.requires),
            "installed": manifest is not None, "current": self.current(runtime_id) if manifest else False,
            "installed_at": (manifest or {}).get("installed_at", ""),
            "download_bytes": self.download_bytes(runtime_id),
        }

    def install(self, runtime_id: str, *, progress: Progress = lambda done, total, message: None,
                cancelled: Cancelled = lambda: False, client: Any = None) -> dict[str, Any]:
        """Download, check and unpack one runtime pack (its base must be installed first).

        Two jobs may want the same pack (two bundles share a Torch layer): the second waits for the first's lock,
        then finds the pack current and returns."""
        pack = self.catalog.runtime(runtime_id)
        if pack.base and not self.installed(pack.base):
            raise PackError(f"{pack.label} stands on {self.catalog.runtime(pack.base).label}; install that first")
        with _pack_lock(self.staging / f"{runtime_id}.lock", cancelled):
            if self.current(runtime_id):
                return self.manifest(runtime_id) or {}
            return self._install(pack, progress=progress, cancelled=cancelled, client=client)

    def _install(self, pack: RuntimePack, *, progress: Progress, cancelled: Cancelled, client: Any) -> dict[str, Any]:
        runtime_id = pack.id
        listed = self.files(runtime_id)
        total = listed.download_bytes
        check_disk(self.root, int(total * (1 + UNPACK_FACTOR)))
        downloads = self.staging / "downloads"
        done = 0

        def advance(count: int) -> None:
            nonlocal done
            done += count
            progress(done, total, f"Downloading {pack.label}")

        wheels: list[Path] = []
        for item in listed.files:
            if cancelled():
                raise PackCancelled("cancelled")
            wheels.append(self._fetch(item, downloads, advance, cancelled, client))
        progress(total, total, f"Unpacking {pack.label}")
        build = self.staging / f"{runtime_id}.build"
        _remove_tree(build)
        build.mkdir(parents=True)
        for wheel in wheels:
            if cancelled():
                _remove_tree(build)
                raise PackCancelled("cancelled")
            install_wheel(wheel, build)
        manifest = {
            "manifest_version": MANIFEST_VERSION,
            "runtime": pack.id,
            "platform": pack.platform,
            "base": pack.base,
            "lock": listed.lock,
            "lock_sha256": listed.lock_sha256,
            "wheels": [{"filename": item.filename, "sha256": item.sha256} for item in listed.files],
            "installed_at": _now(),
        }
        (build / MANIFEST).write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
        target = self.folder(runtime_id)
        self.runtimes.mkdir(parents=True, exist_ok=True)
        retired = None
        if target.exists():
            # An update: the old pack moves aside first, so a failed rename leaves the working one.
            retired = self.runtimes / f".{runtime_id}.old-{int(time.time())}"
            target.rename(retired)
        try:
            build.rename(target)
        except OSError:
            if retired is not None:
                retired.rename(target)
            raise
        if retired is not None:
            _remove_tree(retired)
        for item in listed.files:
            if item.source == "index":
                (downloads / item.filename).unlink(missing_ok=True)
        return manifest

    def _fetch(self, item: PackFile, downloads: Path, advance: Callable[[int], None], cancelled: Cancelled,
               client: Any) -> Path:
        if item.source == "bundled":
            wheel = wheelhouse() / item.filename
            if not wheel.is_file() or _sha256(wheel) != item.sha256:
                raise PackError(f"the bundled {item.filename} is missing or changed; reinstall Omnix")
            return wheel
        return download_file(item.url, downloads / item.filename, sha256=item.sha256, size=item.size,
                             progress=advance, cancelled=cancelled, client=client)

    def verify(self, runtime_id: str) -> list[str]:
        """A full check: the manifest matches this build's file list and every installed file its RECORD digest."""
        manifest = self.manifest(runtime_id)
        if manifest is None:
            return ["not installed"]
        problems = []
        if not self.current(runtime_id):
            problems.append("installed from an older file list; update it")
        problems += verify_installed(self.site(runtime_id))
        return problems

    def remove(self, runtime_id: str, *, needed_by: Iterable[str] = ()) -> None:
        pack = self.catalog.runtime(runtime_id)
        installed_dependents = [item for item in self.catalog.dependents(runtime_id) if self.installed(item)]
        if installed_dependents:
            labels = ", ".join(self.catalog.runtime(item).label for item in installed_dependents)
            raise PackError(f"{pack.label} is needed by {labels}; remove those first")
        blockers = list(needed_by)
        if blockers:
            raise PackError(f"{pack.label} is needed by {', '.join(blockers)}; remove those first")
        _remove_tree(self.folder(runtime_id))


# Model packs --------------------------------------------------------------------------------------------------


@dataclass
class ModelStore:
    cache: Path
    catalog: Catalog

    @property
    def markers(self) -> Path:
        return self.cache / ".omnix"

    def entry(self, model_id: str) -> ModelEntry:
        entry = self.catalog.model(model_id)
        if not entry.pinned:
            raise PackError(f"{entry.label} is downloaded by its own package on first use, not installed here")
        return entry

    def snapshot(self, model_id: str) -> Path:
        from app.models.downloads import snapshot_dir

        return snapshot_dir(self.entry(model_id), cache_dir=self.cache)

    def installed(self, model_id: str) -> bool:
        from app.models.downloads import is_present

        entry = self.entry(model_id)
        return (self.markers / f"{entry.id}.json").is_file() and is_present(entry, cache_dir=self.cache)

    def marker(self, model_id: str) -> dict[str, Any] | None:
        try:
            data = json.loads((self.markers / f"{self.entry(model_id).id}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def install(self, model_id: str, *, token: str | None = None, progress: Progress = lambda d, t, m: None,
                cancelled: Cancelled = lambda: False, fetch: Any = None) -> dict[str, Any]:
        entry = self.entry(model_id)
        if entry.licence.gated and not token:
            raise PackError(f"{entry.label} is gated: accept its terms on Hugging Face and add a token")
        with _pack_lock(self.markers / f"{entry.id}.lock", cancelled):
            if self.installed(entry.id):
                return {**(self.marker(entry.id) or {}), "snapshot": str(self.snapshot(entry.id))}
            return self._install(entry, token=token, progress=progress, cancelled=cancelled, fetch=fetch)

    def _install(self, entry: ModelEntry, *, token: str | None, progress: Progress, cancelled: Cancelled,
                 fetch: Any) -> dict[str, Any]:
        from app.models.downloads import ModelDownloadError, download

        missing = sum(item.size for item in entry.files)
        check_disk(self.cache, missing)
        done = 0

        def on_file(item: Any) -> None:
            nonlocal done
            done += item.size
            if cancelled():
                raise PackCancelled("cancelled")
            progress(done, entry.size, f"Downloading {entry.label}")

        kwargs: dict[str, Any] = {"cache_dir": self.cache, "token": token, "on_file": on_file}
        if fetch is not None:
            kwargs["fetch"] = fetch
        try:
            snapshot = download(entry, **kwargs)
        except ModelDownloadError as exc:
            raise PackError(str(exc)) from exc
        marker = {"model_id": entry.id, "repo": entry.repo, "commit": entry.revision, "licence": entry.licence.id,
                  "installed_at": _now()}
        self.markers.mkdir(parents=True, exist_ok=True)
        (self.markers / f"{entry.id}.json").write_text(json.dumps(marker, indent=1) + "\n", encoding="utf-8")
        return {**marker, "snapshot": str(snapshot)}

    def verify(self, model_id: str) -> list[str]:
        from app.models.downloads import verify

        if not self.installed(model_id):
            return ["not installed"]
        return verify(self.entry(model_id), cache_dir=self.cache)

    def disk_bytes(self, model_id: str) -> int:
        entry = self.entry(model_id)
        folder = self.cache / ("models--" + entry.repo.replace("/", "--"))
        return _folder_bytes(folder) if folder.exists() else 0

    def remove(self, model_id: str) -> None:
        entry = self.entry(model_id)
        (self.markers / f"{entry.id}.json").unlink(missing_ok=True)
        others = [item for item in self.catalog.models.values()
                  if item.id != entry.id and item.repo == entry.repo and self.installed(item.id)]
        if not others:
            _remove_tree(self.cache / ("models--" + entry.repo.replace("/", "--")))


# The installed set --------------------------------------------------------------------------------------------


def runtime_store(catalog: Catalog | None = None) -> RuntimeStore:
    root = packs_root()
    if root is None:
        raise PackError("this Omnix does not manage packs (OMNIX_PACKS_DIR is not set)")
    return RuntimeStore(root, catalog or model_catalog.load())


def model_store(catalog: Catalog | None = None) -> ModelStore:
    root = packs_root()
    if root is None:
        raise PackError("this Omnix does not manage packs (OMNIX_PACKS_DIR is not set)")
    cache = environment().get("HF_HUB_CACHE", "").strip()
    return ModelStore(Path(cache) if cache else root / "models", catalog or model_catalog.load())


def runtime_for_service(service: str, platform: str | None = None, catalog: Catalog | None = None) -> RuntimePack | None:
    """The installed runtime pack a model service runs in on this platform, if any."""
    found = catalog or model_catalog.load()
    wanted = platform or model_catalog.current_platform()
    store = runtime_store(found)
    for pack in found.runtimes.values():
        if pack.service == service and pack.platform == wanted and store.installed(pack.id):
            return pack
    return None


def service_python_path(runtime_id: str, catalog: Catalog | None = None) -> list[Path]:
    """The package folders a service process imports from, overlay first, then its Torch layer."""
    found = catalog or model_catalog.load()
    store = runtime_store(found)
    pack = found.runtime(runtime_id)
    folders = [store.site(pack.id)]
    if pack.base:
        folders.append(store.site(pack.base))
    return folders



__all__ = [
    "ModelStore", "PackCancelled", "PackError", "RuntimeStore", "check_disk", "desktop_mode", "download_file",
    "model_store", "packs_root", "runtime_for_service", "runtime_store", "service_python_path", "wheelhouse",
]
