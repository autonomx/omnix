"""Phase 15.0 — Durable session save/load to disk-backed JSON snapshots.

Provides versioned, migration-safe, disk-backed session persistence.
Never trusts raw disk payloads; normalizes input on load.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.rpg.session.session_store import _safe_dict, _safe_list, _normalize_session


_SESSION_DIR = Path("data/rpg_sessions")
_SAVE_VERSION = "1.0"


def ensure_session_dir() -> Path:
    """Create session directory if it doesn't exist."""
    _SESSION_DIR.mkdir(parents=True, exist_ok=True)
    return _SESSION_DIR


def _session_path(session_id: str) -> Path:
    """Get the file path for a session."""
    safe_id = "".join(ch for ch in str(session_id) if ch.isalnum() or ch in {"-", "_", ":"})
    return ensure_session_dir() / f"{safe_id}.json"


def save_session_to_disk(session: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize and persist session to disk-backed JSON."""
    session = _normalize_session(session)
    manifest = _safe_dict(session.get("manifest"))
    payload = {
        "save_version": _SAVE_VERSION,
        "session": session,
    }
    path = _session_path(manifest.get("id", "session"))
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return session


def load_session_from_disk(session_id: str) -> Optional[Dict[str, Any]]:
    """Load and normalize a session from disk. Returns None if not found."""
    path = _session_path(session_id)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    session = _safe_dict(payload.get("session"))
    return _normalize_session(session)


def list_sessions_from_disk() -> List[Dict[str, Any]]:
    """List all persisted sessions from disk, normalized and sorted."""
    ensure_session_dir()
    sessions: List[Dict[str, Any]] = []
    for path in sorted(_SESSION_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            session = _normalize_session(_safe_dict(payload.get("session")))
            sessions.append(session)
        except Exception:
            continue
    return sessions