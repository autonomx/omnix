"""Watch folders (Voice Studio Phase 7): new recordings in an operator-chosen folder run through a recipe.

Folders are operator configuration (``OMNIX_VOICE_WATCH_FOLDERS``: a JSON list,
or the path of a JSON file holding one), never a user setting. Each names its
input and paired output folder, the recipe, and the workspace and owner its
jobs act for.

- Paths are canonicalised, and a folder whose path has a junction, a symlink or
  a UNC share anywhere in it is refused; so are linked files inside it. Outputs
  are written only under the paired output folder.
- One watcher per folder holds a lease (``omnix_voice_watch_leases``), renewed
  each tick, so one host scans a folder at a time; a host that cannot see the
  folder never takes it. The ledger, not the lease, is what keeps two workers
  from taking the same file: a file is claimed by inserting its row.
- The ledger (``omnix_voice_watch_items``) is unique on workspace, folder,
  relative path and content hash: a restart never processes a file twice. A
  file is claimed in the ledger before it is imported; a claim whose batch never
  started is retried after ``RECLAIM_AFTER_SECONDS``.
- An output keeps the input's relative path and name (``talk.wav`` ->
  ``talk.vocals.wav``, ``talk.srt``), so a re-run overwrites rather than duplicates.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import socket
import stat
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LEASE_SECONDS = 30.0
STABLE_SECONDS = 2.0
RECLAIM_AFTER_SECONDS = 600.0
AUDIO_EXTENSIONS = (".wav", ".flac", ".mp3", ".ogg", ".m4a", ".webm")
MIME = {".wav": "audio/wav", ".flac": "audio/flac", ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".m4a": "audio/mp4",
        ".webm": "audio/webm"}


class WatchFolderRefused(ValueError):
    """The folder's configuration or path is not allowed."""


def _is_link(path: Path) -> bool:
    """A symlink, or (on Windows) any reparse point: junctions included."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def safe_folder(value: str) -> Path:
    """The canonical folder, refusing UNC paths and links anywhere along it."""
    raw = str(value or "").strip()
    if not raw:
        raise WatchFolderRefused("the folder is empty")
    if raw.startswith(("\\\\", "//")):
        raise WatchFolderRefused(f"{raw}: network (UNC) paths are not allowed")
    path = Path(raw)
    if not path.is_absolute():
        raise WatchFolderRefused(f"{raw}: use an absolute path")
    for ancestor in [*reversed(path.parents), path]:
        if _is_link(ancestor):
            raise WatchFolderRefused(f"{raw}: {ancestor} is a junction or symlink")
    resolved = path.resolve()
    if str(resolved).startswith(("\\\\", "//")):
        raise WatchFolderRefused(f"{raw}: it resolves to a network path")
    return resolved


def inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root)
    except ValueError:
        return False
    return True


@dataclass
class WatchFolder:
    id: str
    input: Path
    output: Path
    recipe_id: str
    workspace_id: str
    owner_user_id: str
    extensions: tuple[str, ...] = AUDIO_EXTENSIONS

    @classmethod
    def from_entry(cls, entry: dict[str, Any]) -> WatchFolder:
        for key in ("id", "path", "output", "recipe_id", "workspace_id", "owner_user_id"):
            if not str(entry.get(key) or "").strip():
                raise WatchFolderRefused(f"a watch folder needs {key}")
        folder_id = str(entry["id"]).strip()
        if not all(char.isalnum() or char in "-_" for char in folder_id):
            raise WatchFolderRefused(f"{folder_id}: ids are letters, digits, - and _")
        source, output = safe_folder(entry["path"]), safe_folder(entry["output"])
        if inside(source, output) or inside(output, source):
            raise WatchFolderRefused(f"{folder_id}: the input and output folders must not contain each other")
        extensions = tuple(str(value).lower() for value in entry.get("extensions") or AUDIO_EXTENSIONS)
        return cls(folder_id, source, output, str(entry["recipe_id"]), str(entry["workspace_id"]),
                   str(entry["owner_user_id"]), extensions)


def configured_folders(raw: str | None = None) -> list[WatchFolder]:
    """The operator's watch folders; a refused entry is logged and left out."""
    if raw is None:
        from app.config.env import env_str

        raw = (env_str("OMNIX_VOICE_WATCH_FOLDERS", "") or "").strip()
    if not raw:
        return []
    text = raw if raw.lstrip().startswith("[") else Path(raw).read_text(encoding="utf-8")
    folders = []
    for entry in json.loads(text):
        try:
            folders.append(WatchFolder.from_entry(entry))
        except (WatchFolderRefused, OSError) as exc:
            logger.warning("Watch folder refused: %s", exc)
    return folders


# --- leases ---------------------------------------------------------------------------------------


def take_lease(folder_id: str, holder_id: str, *, seconds: float = LEASE_SECONDS) -> int | None:
    """Take or renew the folder's lease; the fence token, or ``None`` while someone else holds it."""
    from app.persistence.database import default_database
    from app.persistence.unit_of_work import unit_of_work

    with unit_of_work(default_database()) as work:
        row = work.connection.execute(
            """INSERT INTO omnix_voice_watch_leases (folder_id, holder_id, lease_expires_at)
               VALUES (%s, %s, clock_timestamp() + (%s * INTERVAL '1 second'))
               ON CONFLICT (folder_id) DO UPDATE
                  SET holder_id = EXCLUDED.holder_id,
                      fence_token = omnix_voice_watch_leases.fence_token
                                    + CASE WHEN omnix_voice_watch_leases.holder_id = EXCLUDED.holder_id THEN 0 ELSE 1 END,
                      lease_expires_at = EXCLUDED.lease_expires_at
                WHERE omnix_voice_watch_leases.holder_id = EXCLUDED.holder_id
                   OR omnix_voice_watch_leases.lease_expires_at <= clock_timestamp()
               RETURNING fence_token""",
            (folder_id, holder_id, max(5.0, float(seconds))),
        ).fetchone()
        work.commit()
    return int(row[0]) if row else None


# --- the watcher ----------------------------------------------------------------------------------


@dataclass
class WatchFolders:
    folders: list[WatchFolder]
    holder_id: str = field(default_factory=lambda: f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}")
    # relative path -> (size, mtime) seen on the previous scan: a file is taken once it stops changing.
    _seen: dict[tuple[str, str], tuple[int, float]] = field(default_factory=dict)

    @classmethod
    def from_configuration(cls) -> WatchFolders | None:
        folders = configured_folders()
        return cls(folders) if folders else None

    def tick(self) -> dict[str, int]:
        taken = 0
        for folder in self.folders:
            if not folder.input.is_dir():
                continue  # this host cannot see it: leave the lease to one that can
            if take_lease(folder.id, self.holder_id) is None:
                continue
            try:
                taken += self.scan(folder)
            except Exception:
                logger.warning("Watch folder %s could not be scanned", folder.id, exc_info=True)
        return {"taken": taken}

    def _stable_files(self, folder: WatchFolder) -> list[tuple[Path, str]]:
        found = []
        now = time.time()
        for path in sorted(folder.input.rglob("*")):
            if not path.is_file() or _is_link(path) or path.suffix.lower() not in folder.extensions:
                continue
            if not inside(folder.input, path):
                continue
            relative = path.relative_to(folder.input).as_posix()
            info = path.stat()
            signature = (info.st_size, info.st_mtime)
            key = (folder.id, relative)
            previous, self._seen[key] = self._seen.get(key), signature
            if previous == signature and now - info.st_mtime >= STABLE_SECONDS and info.st_size > 0:
                found.append((path, relative))
        return found

    def scan(self, folder: WatchFolder) -> int:
        """Claim new, settled files in the ledger, import them, and start one batch for them."""
        from app.persistence.identity_service import PostgresIdentityRepository
        from app.persistence.tenant_scope import system_scope
        from app.runtime.tenant_context import pop_tenant, push_tenant

        files = self._stable_files(folder)
        if not files:
            return 0
        with system_scope("voice.automation"), _work() as work:
            context = PostgresIdentityRepository(work.connection).load_context(
                user_id=folder.owner_user_id, workspace_id=folder.workspace_id)
            work.rollback()
        token = push_tenant(context)
        try:
            claimed = [(path, relative, digest) for path, relative in files
                       if (digest := _sha256(path)) and self._claim(folder, relative, digest)]
            # A claim retaken after a crash between starting its batch and recording it: that batch has it.
            started = {(relative, digest): item_id for _path, relative, digest in claimed
                       if (item_id := self._started_item(folder, relative, digest))}
            for (relative, digest), item_id in started.items():
                self._record(folder, relative, digest, item_id)
            claimed = [entry for entry in claimed if (entry[1], entry[2]) not in started]
            if not claimed:
                return 0
            from .automation import start_batch

            assets = {self._import(folder, path, relative, digest): relative for path, relative, digest in claimed}
            run = start_batch(recipe_id=folder.recipe_id, asset_ids=list(assets), title=f"Watch: {folder.id}",
                              watch_folder=folder.id, output_names=assets)
            for item in run["items"]:
                self._record(folder, assets[item["source_asset_id"]], item["input_hash"], item["id"])
                if item["status"] == "skipped":  # done before at this recipe version: its earlier outputs
                    try:
                        self.deliver(run, item)
                    except OSError:
                        logger.warning("Watch folder %s: outputs for %s could not be written", folder.id,
                                       item["output_name"], exc_info=True)
            return len(claimed)
        finally:
            pop_tenant(token)

    @staticmethod
    def _claim(folder: WatchFolder, relative: str, digest: str) -> bool:
        """Claim a file once: a new ledger row, or one whose batch never started (a crash in between)."""
        context = _tenant()
        with _work() as work:
            row = work.connection.execute(
                """INSERT INTO omnix_voice_watch_items (id, workspace_id, folder_id, relative_path, content_hash)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (workspace_id, folder_id, relative_path, content_hash) DO UPDATE
                      SET created_at = clock_timestamp()
                    WHERE omnix_voice_watch_items.batch_item_id = ''
                      AND omnix_voice_watch_items.created_at < clock_timestamp() - (%s * INTERVAL '1 second')
                   RETURNING id""",
                (f"vwatch:{uuid.uuid4().hex}", context.workspace_id, folder.id, relative, digest, RECLAIM_AFTER_SECONDS),
            ).fetchone()
            work.commit()
        return row is not None

    @staticmethod
    def _started_item(folder: WatchFolder, relative: str, digest: str) -> str:
        """The batch item a run of this folder already has for this file, if one does."""
        context = _tenant()
        with _work() as work:
            row = work.connection.execute(
                """SELECT item.id FROM omnix_voice_batch_items AS item
                     JOIN omnix_voice_batch_runs AS run ON run.workspace_id = item.workspace_id AND run.id = item.run_id
                    WHERE item.workspace_id = %s AND run.watch_folder = %s AND item.output_name = %s
                      AND item.input_hash = %s
                    ORDER BY item.updated_at DESC LIMIT 1""",
                (context.workspace_id, folder.id, relative, digest)).fetchone()
            work.rollback()
        return str(row[0]) if row else ""

    @staticmethod
    def _record(folder: WatchFolder, relative: str, digest: str, item_id: str) -> None:
        context = _tenant()
        with _work() as work:
            work.connection.execute(
                """UPDATE omnix_voice_watch_items SET batch_item_id = %s
                    WHERE workspace_id = %s AND folder_id = %s AND relative_path = %s AND content_hash = %s""",
                (item_id, context.workspace_id, folder.id, relative, digest))
            work.commit()

    @staticmethod
    def _import(folder: WatchFolder, path: Path, relative: str, digest: str) -> str:
        from datetime import datetime, timezone

        from app.assets import AssetRecord, AssetType, default_asset_store
        from app.runtime.paths import resources_data_root

        target = resources_data_root() / "voice_studio" / "watch" / folder.id / f"{digest}{path.suffix.lower()}"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        asset = default_asset_store().upsert_asset(AssetRecord(
            id=f"audio:watch-{folder.id}-{hashlib.sha256(relative.encode('utf-8')).hexdigest()[:12]}-{digest[:24]}",
            module="voice", type=AssetType.AUDIO,
            mime_type=MIME.get(path.suffix.lower(), "audio/wav"), storage_path=str(target),
            metadata={"title": relative, "source": "watch_folder", "watch_folder": folder.id, "file_name": path.name},
            created_at=datetime.now(timezone.utc).isoformat(), compat={"contract": "voice_watch_import_v1"},
        ))
        return asset.id

    def deliver(self, run: dict[str, Any], item: dict[str, Any]) -> None:
        """Write a finished item's outputs under the folder's output folder, beside its relative path."""
        folder = next((entry for entry in self.folders if entry.id == run.get("watch_folder")), None)
        if folder is None or not item.get("output_name"):
            return
        if not folder.output.is_dir():
            logger.warning("Watch folder %s: the output folder is not visible from this host", folder.id)
            return
        from app.assets import default_asset_store
        from app.assets.content import open_asset

        store = default_asset_store()
        relative = Path(item["output_name"])
        if relative.is_absolute() or ".." in relative.parts:
            logger.warning("Watch folder %s: refused output name %s", folder.id, relative)
            return
        for output in item.get("outputs") or []:
            asset = store.get_asset(str(output.get("asset_id") or "")) if output.get("asset_id") else None
            if asset is None:
                continue
            suffix = Path(asset.storage_path or "").suffix or ".bin"
            tag = str(output.get("kind") or output.get("tool") or "output").replace("stem_", "").replace("subtitles_", "")
            name = f"{relative.stem}{suffix}" if tag in {"srt", "vtt", "txt"} else f"{relative.stem}.{tag}{suffix}"
            target = folder.output / relative.parent / name
            # Resolving catches a junction someone made inside the output folder since the check at start.
            if not inside(folder.output, target.parent) or _is_link(target):
                logger.warning("Watch folder %s: refused to write %s", folder.id, target)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_name(target.name + ".partial")
            if _is_link(partial):
                logger.warning("Watch folder %s: refused to write through the link %s", folder.id, partial)
                continue
            partial.unlink(missing_ok=True)  # a leftover from a crash
            # "x": created here, never opened through something planted since the check above.
            with open_asset(asset) as source, partial.open("xb") as handle:
                shutil.copyfileobj(source, handle)
            os.replace(partial, target)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _work() -> Any:
    from app.persistence.database import default_database
    from app.persistence.unit_of_work import unit_of_work

    return unit_of_work(default_database())


def _tenant() -> Any:
    from app.runtime.tenant_context import current_tenant

    return current_tenant()


__all__ = ["WatchFolder", "WatchFolderRefused", "WatchFolders", "configured_folders", "inside", "safe_folder",
           "take_lease"]
