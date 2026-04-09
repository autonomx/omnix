"""Phase 15.3 — Canonical session service."""
from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.session.ambient_builder import (
    ensure_ambient_runtime_state,
    normalize_ambient_state,
)
from app.rpg.session.durable_store import (
    archive_session_on_disk,
    list_sessions_from_disk,
    load_session_from_disk,
    save_session_to_disk,
)
from app.rpg.session.migrations import migrate_session_payload
from app.rpg.session.package_bridge import package_to_session, session_to_package
from app.rpg.validation.integrity import (
    assert_package_integrity,
    assert_session_integrity,
    validate_session_integrity,
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def create_or_normalize_session(session: Dict[str, Any]) -> Dict[str, Any]:
    session = _safe_dict(session)
    session = migrate_session_payload(session)
    manifest = _safe_dict(session.get("manifest"))
    session["manifest"] = manifest
    session.setdefault("installed_packs", [])
    session.setdefault("simulation_state", {})
    # Living-world: ensure ambient runtime state exists and is bounded
    runtime_state = _safe_dict(session.get("runtime_state"))
    runtime_state = ensure_ambient_runtime_state(runtime_state)
    runtime_state = normalize_ambient_state(runtime_state)
    session["runtime_state"] = runtime_state
    return session


def save_session(session: Dict[str, Any]) -> Dict[str, Any]:
    session = create_or_normalize_session(session)
    assert_session_integrity(session)
    return save_session_to_disk(session)


def load_session(session_id: str) -> Dict[str, Any]:
    session = load_session_from_disk(session_id)
    if session is None:
        return None
    # Fix #2: soft validation on load — allow recovery / migration of older sessions
    session = create_or_normalize_session(session)
    validate_session_integrity(session)  # log but don't fail
    return session


def list_sessions() -> List[Dict[str, Any]]:
    sessions = list_sessions_from_disk()
    out = []
    for item in sessions:
        item = create_or_normalize_session(item)
        # Fix #3: attach integrity info instead of hiding invalid sessions
        integrity = validate_session_integrity(item)
        item["_integrity"] = integrity
        out.append(item)
    return out


def archive_session(session_id: str) -> Dict[str, Any]:
    return archive_session_on_disk(session_id)


def export_session_as_package(session: Dict[str, Any]) -> Dict[str, Any]:
    session = create_or_normalize_session(session)
    assert_session_integrity(session)
    return session_to_package(session)


def import_session_from_package(package_payload: Dict[str, Any]) -> Dict[str, Any]:
    assert_package_integrity(package_payload)
    result = package_to_session(package_payload)
    if not result.get("ok"):
        return result
    session = create_or_normalize_session(_safe_dict(result.get("session")))
    assert_session_integrity(session)
    return {"ok": True, "session": session}
