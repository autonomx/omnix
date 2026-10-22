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
import sys
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


class PackRetryable(PackError):
    """The pack could not be changed now, but a later attempt may succeed; the job is retried."""


class PackDownloadError(PackRetryable):
    """A download failed in a way a later attempt may not (a server or network error, a corrupted transfer)."""


class PackBusy(PackRetryable):
    """A pack folder is in use (its model service still has it loaded)."""


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


def _compile_bytecode(site: Path, *, final: Path) -> None:
    """Compiles the pack's bytecode once, at install, into its own ``__pycache__`` folders.

    A service's first run otherwise compiles every module it imports, and on Windows a speech service whose first
    run did so stopped accepting connections (its first live call never connected; every later start worked). The
    paths in tracebacks name the folder the pack is renamed to (``final``), not the staging folder.

    Each file's output is named explicitly: ``compileall`` would follow the job worker's ``PYTHONPYCACHEPREFIX`` and
    write into the shared cache folder, where no service looks."""
    import py_compile

    if not site.is_dir():
        return
    tag = sys.implementation.cache_tag
    for source in site.rglob("*.py"):
        relative = source.relative_to(site)
        target = source.parent / "__pycache__" / f"{source.stem}.{tag}.pyc"
        try:
            py_compile.compile(str(source), cfile=str(target), dfile=str(final / relative), doraise=True,
                               invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
        except (py_compile.PyCompileError, OSError, ValueError):
            continue  # a file that does not compile (a template, Python 2 code) is compiled, or not, on import


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

        with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(60.0, read=300.0),
                          headers={"User-Agent": "omnix-desktop"}) as own_client:
            return download_file(url, target, sha256=sha256, size=size, progress=progress, cancelled=cancelled,
                                 client=own_client)
    try:
        _stream_to(partial, url, size=size, progress=progress, cancelled=cancelled, client=client)
    except PackError:
        raise
    except Exception as exc:  # noqa: BLE001 - httpx's transport errors and OSErrors alike: the next attempt resumes
        raise PackDownloadError(f"download interrupted ({type(exc).__name__}): {url}") from exc
    actual = _sha256(partial)
    if actual != sha256:
        partial.unlink(missing_ok=True)
        raise PackDownloadError(f"{target.name} has SHA-256 {actual}, expected {sha256}; it was deleted, try again")
    partial.replace(target)
    return target


def _stream_to(partial: Path, url: str, *, size: int | None, progress: Callable[[int], None], cancelled: Cancelled,
               client: Any) -> None:
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
        elif response.status_code >= 500 or response.status_code == 429:
            raise PackDownloadError(f"download failed ({response.status_code}), try again later: {url}")
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

    def updating(self, runtime_id: str) -> bool:
        """A new version is about to replace this pack: its services stop until the swap is done."""
        return (self.staging / f"{runtime_id}.updating").exists()

    def present(self, runtime_id: str) -> bool:
        """The pack's folder exists, complete or not (a removal that failed part-way leaves no manifest)."""
        return self.folder(runtime_id).exists()

    def sweep(self) -> None:
        """Deletes folders an interrupted update or removal left aside (``.<id>.old-*``, ``.<id>.removing-*``)."""
        if not self.runtimes.is_dir():
            return
        for leftover in self.runtimes.glob(".*"):
            if leftover.is_dir() and (".old-" in leftover.name or ".removing-" in leftover.name):
                try:
                    _remove_tree(leftover)
                except OSError:
                    logger.info("Could not delete %s yet", leftover)

    def current(self, runtime_id: str) -> bool:
        """Installed from the file list this build ships (an app update can change it), on the base it ships."""
        manifest = self.manifest(runtime_id)
        if manifest is None or manifest.get("lock_sha256") != self.files(runtime_id).lock_sha256:
            return False
        base = self.catalog.runtime(runtime_id).base
        return not base or manifest.get("base_lock_sha256") == self.files(base).lock_sha256

    def runnable(self, runtime_id: str) -> bool:
        """Installed, not being replaced, and (an overlay) built for the base that is installed now.

        An out-of-date pack keeps running until its update is installed, but an overlay never runs on a Torch layer
        it was not built for: torchvision and NeMo are bound to the Torch they were locked with."""
        manifest = self.manifest(runtime_id)
        if manifest is None or self.updating(runtime_id):
            return False
        base = self.catalog.runtime(runtime_id).base
        if not base:
            return True
        installed_base = self.manifest(base)
        return installed_base is not None and manifest.get("base_lock_sha256") == installed_base.get("lock_sha256")

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
                cancelled: Cancelled = lambda: False, client: Any = None,
                before_swap: Callable[[str], None] = lambda runtime_id: None) -> dict[str, Any]:
        """Download, check and unpack one runtime pack (its base must be installed first).

        Two jobs may want the same pack (two bundles share a Torch layer): the second waits for the first's lock,
        then finds the pack current and returns.

        An update keeps the old pack running until the new one is unpacked. Then the pack is marked as updating
        (the supervisor stops the services that stand on it), ``before_swap`` waits for them to stop, and the new
        folder replaces the old one."""
        pack = self.catalog.runtime(runtime_id)
        if pack.base and not self.installed(pack.base):
            raise PackError(f"{pack.label} stands on {self.catalog.runtime(pack.base).label}; install that first")
        with _pack_lock(self.staging / f"{runtime_id}.lock", cancelled):
            self.sweep()
            if self.current(runtime_id):
                return self.manifest(runtime_id) or {}
            return self._install(pack, progress=progress, cancelled=cancelled, client=client, before_swap=before_swap)

    def _install(self, pack: RuntimePack, *, progress: Progress, cancelled: Cancelled, client: Any,
                 before_swap: Callable[[str], None]) -> dict[str, Any]:
        runtime_id = pack.id
        listed = self.files(runtime_id)
        total = listed.download_bytes
        check_disk(self.root, int(total * (1 + UNPACK_FACTOR)))
        # Each pack downloads into its own folder: overlays installing at once share many wheel filenames.
        downloads = self.staging / "downloads" / runtime_id
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
        progress(total, total, f"Preparing {pack.label}")
        _compile_bytecode(build / "site", final=self.site(runtime_id))
        manifest = {
            "manifest_version": MANIFEST_VERSION,
            "runtime": pack.id,
            "platform": pack.platform,
            "base": pack.base,
            # The base this overlay was built on: an overlay never runs on another (``runnable``).
            "base_lock_sha256": (self.manifest(pack.base) or {}).get("lock_sha256", "") if pack.base else "",
            "lock": listed.lock,
            "lock_sha256": listed.lock_sha256,
            "wheels": [{"filename": item.filename, "sha256": item.sha256} for item in listed.files],
            "installed_at": _now(),
        }
        (build / MANIFEST).write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
        target = self.folder(runtime_id)
        self.runtimes.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            build.rename(target)
            _remove_tree(downloads)
            return manifest
        marker = self.staging / f"{runtime_id}.updating"
        marker.write_text(_now(), encoding="utf-8")
        try:
            before_swap(runtime_id)
            # The old pack moves aside first, so a failed rename leaves the working one.
            retired = self.runtimes / f".{runtime_id}.old-{int(time.time())}"
            try:
                target.rename(retired)
            except OSError as exc:
                raise PackBusy(f"{pack.label} is still in use by its model service; trying again shortly") from exc
            try:
                build.rename(target)
            except OSError:
                retired.rename(target)
                raise
        finally:
            marker.unlink(missing_ok=True)
        try:
            _remove_tree(retired)
        except OSError:
            logger.info("Could not delete %s yet; it is deleted on the next install or removal", retired)
        _remove_tree(downloads)
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
        folder = self.folder(runtime_id)
        if not folder.exists():
            return
        # Moved aside first, so a pack is never left half-deleted under its own name: on Windows the rename fails
        # while a service has the pack's DLLs loaded, and the job retries once the service has stopped.
        aside = self.runtimes / f".{runtime_id}.removing-{int(time.time())}"
        try:
            folder.rename(aside)
        except OSError as exc:
            raise PackBusy(f"{pack.label} is still in use by its model service; trying again shortly") from exc
        try:
            _remove_tree(aside)
        except OSError:
            logger.info("Could not delete %s yet; it is deleted on the next install or removal", aside)
        self.sweep()


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
            # A file that failed its digest or a transfer that broke off: a later attempt may succeed.
            raise PackDownloadError(str(exc)) from exc
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
        others = [item for item in self.catalog.models.values()
                  if item.id != entry.id and item.repo == entry.repo and self.installed(item.id)]
        if not others:
            _remove_tree(self.cache / ("models--" + entry.repo.replace("/", "--")))
        # Last: a removal that failed part-way still shows as installed, so its retry finishes it.
        (self.markers / f"{entry.id}.json").unlink(missing_ok=True)


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
