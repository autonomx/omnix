"""RPG session compatibility helpers for gateway bridge routes."""
from __future__ import annotations

from typing import Any


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def list_rpg_sessions_payload() -> dict[str, Any]:
    """Return the legacy RPG session list envelope without importing API routers."""
    from app.rpg.session.service import list_sessions

    return {"ok": True, "sessions": list_sessions() or []}


def get_rpg_session_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Return the legacy RPG session inspection envelope for a session id."""
    from app.rpg.session.runtime import build_frontend_bootstrap_payload, load_runtime_session

    session_id = _safe_str(_safe_dict(data).get("session_id")).strip()
    if not session_id:
        return {"ok": False, "error": "missing_session_id"}

    session = load_runtime_session(session_id)
    if not session:
        return {"ok": False, "error": "session_not_found", "session_id": session_id}

    game = _safe_dict(build_frontend_bootstrap_payload(session))
    if game.get("session_id") == "session:unknown":
        game["session_id"] = session_id
    return {"ok": True, "game": game}
