"""Phase 13.5 — Session lifecycle + persistence module.

Provides bounded, normalized session registry management.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

_MAX_SESSIONS = 64


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = _safe_str(value).strip()
        if text:
            return text
    return ""


def _normalize_session(value: Any) -> Dict[str, Any]:
    """Normalize a session record into bounded deterministic state."""
    data = _safe_dict(value)
    manifest = _safe_dict(data.get("manifest"))
    state = _safe_dict(data.get("state"))
    return {
        "manifest": {
            "id": _safe_str(manifest.get("id")).strip(),
            "schema_version": int(manifest.get("schema_version") or 2),
            "title": _safe_str(manifest.get("title")).strip(),
            "status": _first_non_empty(manifest.get("status"), "active"),
            "created_at": _safe_str(manifest.get("created_at")).strip(),
            "updated_at": _safe_str(manifest.get("updated_at")).strip(),
            "source_pack_id": _safe_str(manifest.get("source_pack_id")).strip(),
            "source_template_id": _safe_str(manifest.get("source_template_id")).strip(),
            "archived": bool(manifest.get("archived")),
        },
        "state": state,
        "setup_payload": _safe_dict(data.get("setup_payload")),
        "simulation_state": _safe_dict(data.get("simulation_state")),
        "runtime_state": _safe_dict(data.get("runtime_state")),
    }


def ensure_session_registry(root_state: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure session registry exists and is normalized."""
    root_state = _safe_dict(root_state)
    sessions = [
        _normalize_session(item)
        for item in _safe_list(root_state.get("sessions"))
        if isinstance(item, dict)
    ]
    sessions = sorted(
        sessions,
        key=lambda item: (
            _safe_str(_safe_dict(item.get("manifest")).get("title")).lower(),
            _safe_str(_safe_dict(item.get("manifest")).get("id")),
        ),
    )[:_MAX_SESSIONS]
    root_state["sessions"] = sessions
    return root_state


def list_sessions(root_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return normalized list of active sessions."""
    root_state = ensure_session_registry(root_state)
    return _safe_list(root_state.get("sessions"))


def save_session(root_state: Dict[str, Any], session: Dict[str, Any]) -> Dict[str, Any]:
    """Save or update a session in the registry (upsert by id)."""
    root_state = ensure_session_registry(root_state)
    sessions = _safe_list(root_state.get("sessions"))
    normalized = _normalize_session(session)

    session_id = _safe_str(_safe_dict(normalized.get("manifest")).get("id"))
    # Remove existing session with same id
    sessions = [
        item for item in sessions
        if _safe_str(_safe_dict(item.get("manifest")).get("id")) != session_id
    ]
    sessions.append(normalized)
    root_state["sessions"] = sorted(
        sessions,
        key=lambda item: (
            _safe_str(_safe_dict(item.get("manifest")).get("title")).lower(),
            _safe_str(_safe_dict(item.get("manifest")).get("id")),
        ),
    )[:_MAX_SESSIONS]
    return root_state


def get_session(root_state: Dict[str, Any], session_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a session by id, or None if not found."""
    for session in list_sessions(root_state):
        if _safe_str(_safe_dict(session.get("manifest")).get("id")) == _safe_str(session_id):
            return session
    return None


def archive_session(root_state: Dict[str, Any], session_id: str) -> Dict[str, Any]:
    """Mark a session as archived without deleting it."""
    root_state = ensure_session_registry(root_state)
    sessions = []
    for session in _safe_list(root_state.get("sessions")):
        session = _normalize_session(session)
        manifest = _safe_dict(session.get("manifest"))
        if _safe_str(manifest.get("id")) == _safe_str(session_id):
            manifest["status"] = "archived"
            session["manifest"] = manifest
        sessions.append(session)
    root_state["sessions"] = sessions[:_MAX_SESSIONS]
    return root_state