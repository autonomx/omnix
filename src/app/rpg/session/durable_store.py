"""Phase 15.0 — Durable session save/load to disk-backed JSON snapshots.

Provides versioned, migration-safe, disk-backed session persistence.
Never trusts raw disk payloads; normalizes input on load.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.rpg.session.migrations import migrate_session_payload
from app.rpg.session.session_store import _normalize_session, _safe_dict
from app.runtime_paths import repo_root, rpg_sessions_root

logger = logging.getLogger(__name__)
_SESSION_DIR = rpg_sessions_root()
_LEGACY_SESSION_DIR = repo_root() / "data" / "rpg_sessions"
_SAVE_VERSION = "1.0"


def _migrate_legacy_sessions():
    """
    One-time migration from data/rpg_sessions → resources/data/rpg_sessions
    Safe, idempotent, deterministic.
    """
    try:
        if _LEGACY_SESSION_DIR.exists() and not _SESSION_DIR.exists():
            logger.warning(
                "[RPG][MIGRATION] Moving legacy sessions → resources/data/rpg_sessions"
            )

            _SESSION_DIR.parent.mkdir(parents=True, exist_ok=True)
            _LEGACY_SESSION_DIR.rename(_SESSION_DIR)

        elif _LEGACY_SESSION_DIR.exists() and _SESSION_DIR.exists():
            logger.warning(
                "[RPG][MIGRATION] Legacy + new both exist. Skipping auto-move."
            )
    except Exception as e:
        logger.error(f"[RPG][MIGRATION] Failed: {e}")


# Run on import (safe, deterministic)
_migrate_legacy_sessions()

# Ensure directory exists
_SESSION_DIR.mkdir(parents=True, exist_ok=True)


def ensure_session_dir() -> Path:
    """Create session directory if it doesn't exist."""
    _SESSION_DIR.mkdir(parents=True, exist_ok=True)
    return _SESSION_DIR


class SessionStoreError(RuntimeError):
    """Base durable-store error."""


class CorruptSessionPayloadError(SessionStoreError):
    """Raised when a persisted session payload is unreadable or invalid."""

    def __init__(self, session_id: str, path: Path, reason: str):
        self.session_id = str(session_id or "").strip()
        self.path = Path(path)
        self.reason = str(reason or "corrupt_session_payload").strip() or "corrupt_session_payload"
        super().__init__(self.reason)


def _session_path(session_id: str) -> Path:
    """Get the file path for a session."""
    safe_id = "".join(ch for ch in str(session_id) if ch.isalnum() or ch in {"-", "_", ":"})
    safe_id = safe_id.replace(":", "_")  # Windows does not allow colons in filenames
    return ensure_session_dir() / f"{safe_id}.json"


def _replace_with_retry(tmp_name: str, path: Path, *, attempts: int = 8, base_delay_s: float = 0.02) -> None:
    """Best-effort Windows-safe atomic replace with short retry/backoff."""
    last_exc = None
    for attempt in range(attempts):
        try:
            os.replace(tmp_name, path)
            return
        except PermissionError as exc:
            last_exc = exc
            if attempt >= attempts - 1:
                break
            time.sleep(base_delay_s * (attempt + 1))
        except OSError as exc:
            last_exc = exc
            if attempt >= attempts - 1:
                break
            time.sleep(base_delay_s * (attempt + 1))

    # Last-resort fallback for Windows file-lock edge cases.
    try:
        text = Path(tmp_name).read_text(encoding="utf-8")
        path.write_text(text, encoding="utf-8")
        return
    except Exception:
        pass
    raise last_exc


def _write_text_atomic(path: Path, text: str) -> None:
    """Write text atomically to avoid truncated/empty session files."""
    ensure_session_dir()
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=f"{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            tmp_name = handle.name
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(tmp_name, path)
    finally:
        if tmp_name:
            try:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)
            except OSError:
                pass


def _quarantine_corrupt_session_file(path: Path) -> Path:
    """Move a corrupt session aside so repeated resume attempts do not crash forever."""
    quarantine_path = path.with_name(f"{path.stem}.corrupt.{int(time.time() * 1000)}{path.suffix}")
    try:
        os.replace(path, quarantine_path)
    except OSError:
        # Best-effort fallback if rename/replace is blocked on Windows.
        quarantine_path.write_text(path.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
        try:
            path.unlink(missing_ok=True)
        except TypeError:
            if path.exists():
                path.unlink()
    return quarantine_path


def _read_payload_json(path: Path, session_id: str) -> Dict[str, Any]:
    """Read raw JSON payload with corruption detection + quarantine."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SessionStoreError(f"session_read_failed:{session_id}") from exc

    if not text.strip():
        quarantined = _quarantine_corrupt_session_file(path)
        logger.error("Quarantined empty RPG session file", extra={"session_id": session_id, "path": str(quarantined)})
        raise CorruptSessionPayloadError(session_id, quarantined, "corrupt_session_payload")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        quarantined = _quarantine_corrupt_session_file(path)
        logger.exception("Quarantined invalid RPG session JSON", extra={"session_id": session_id, "path": str(quarantined)})
        raise CorruptSessionPayloadError(session_id, quarantined, "corrupt_session_payload")

    return _safe_dict(payload)


def save_session_to_disk(session: Dict[str, Any], *, compact: bool = False) -> Dict[str, Any]:
    """Normalize, migrate, and persist session to disk-backed JSON."""
    session = _normalize_session(session)
    session = migrate_session_payload(session)
    manifest = _safe_dict(session.get("manifest"))
    payload = {
        "save_version": _SAVE_VERSION,
        "session": session,
    }
    path = _session_path(manifest.get("session_id") or manifest.get("id") or "session")
    if compact:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(payload, indent=2, ensure_ascii=False)
    _write_text_atomic(path, text)
    return session


def load_session_from_disk(session_id: str) -> Optional[Dict[str, Any]]:
    """Load and normalize a session from disk with migration. Returns None if not found."""
    path = _session_path(session_id)
    if not path.exists():
        return None
    raw_payload = _read_payload_json(path, session_id)
    migrated = migrate_session_payload(raw_payload)
    return _normalize_session(_safe_dict(migrated.get("session")))


def list_sessions_from_disk() -> List[Dict[str, Any]]:
    """List all persisted sessions from disk with migration, normalized and sorted."""
    ensure_session_dir()
    sessions: List[Dict[str, Any]] = []
    for path in sorted(_SESSION_DIR.glob("*.json")):
        try:
            session_id = path.stem
            raw_payload = _read_payload_json(path, session_id)
            migrated = migrate_session_payload(raw_payload)
            session = _normalize_session(_safe_dict(migrated.get("session")))
            sessions.append(session)
        except CorruptSessionPayloadError:
            # Corrupt files are quarantined by _read_payload_json; skip them here.
            continue
        except Exception:
            logger.exception("Failed to list RPG session from disk", extra={"path": str(path)})
            continue
    return sessions


def archive_session_on_disk(session_id: str) -> Dict[str, Any]:
    """Archive a session on disk by setting archived=True in manifest and persisting."""
    session = load_session_from_disk(session_id)
    if session is None:
        return {"ok": False, "error": "session_not_found"}
    manifest = _safe_dict(session.get("manifest"))
    manifest["archived"] = True
    session["manifest"] = manifest
    save_session_to_disk(session)
    return {"ok": True, "session": session}
