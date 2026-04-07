"""Phase 15.0 — Migration layer for session payloads.

Provides versioned migration support for old/unversioned saves.
Ensures saves are always normalized to the current schema version.
"""
from __future__ import annotations

from typing import Any, Dict


_CURRENT_SAVE_VERSION = "1.0"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def migrate_session_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate a session payload from an older schema to the current version.

    This is a placeholder migration path for older/unversioned saves.
    Future versions should expand this to handle specific schema changes.
    """
    payload = _safe_dict(payload)
    version = payload.get("save_version")
    if version == _CURRENT_SAVE_VERSION:
        return payload

    # Placeholder migration path for older/unversioned saves
    return {
        "save_version": _CURRENT_SAVE_VERSION,
        "session": _safe_dict(payload.get("session")),
    }