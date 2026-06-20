"""Gateway compatibility bridge for Campaign Genesis v2 launches."""

from __future__ import annotations

from typing import Any

from app.platform.rpg_session_compat import get_rpg_session_payload as _legacy_get_rpg_session_payload
from app.rpg.session.genesis.promoted_launch import create_promoted_new_game


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def get_rpg_session_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Promote new-game requests into genesis before falling back to compat."""

    payload = _safe_dict(data)
    action = _safe_str(payload.get("action")).strip()
    request = _safe_dict(payload.get("request") or payload)
    if action == "new_game" and request:
        return create_promoted_new_game(payload)
    return _legacy_get_rpg_session_payload(data)
