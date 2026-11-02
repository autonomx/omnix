"""RPG session compatibility helpers for gateway bridge routes."""
from __future__ import annotations

from typing import Any
from app.apps.rpg.foundation.safe_values import safe_dict as _safe_dict


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _load_mutable_session(session_id: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    from app.apps.rpg.session.service import load_session

    session = load_session(session_id)
    if not session:
        return None, {}
    state = _safe_dict(session.get("state"))
    session["state"] = state
    return session, state


def list_rpg_sessions_payload() -> dict[str, Any]:
    """Return the legacy RPG session list envelope plus launch presets."""
    from app.apps.rpg.session.new_game import list_rpg_presets
    from app.apps.rpg.session.service import list_sessions

    presets_payload = list_rpg_presets()
    return {
        "ok": True,
        "sessions": list_sessions() or [],
        "presets": presets_payload.get("presets", []),
    }


def get_rpg_session_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Return a session envelope or perform a synchronous RPG action.

    This gateway-compat route is used by the web app while typed RPG endpoints
    are being promoted. Supported actions are synchronous and do not call
    LLM/image/TTS services:

    - {"action": "new_game", ...}
    - {"action": "start_preset", "preset_id": "demo_glimmerdeep_pass_lvl14"}
    - {"action": "continue", "session_id": "..."}
    - {"action": "rename", "session_id": "...", "name": "..."}
    - {"action": "delete", "session_id": "..."}
    - {"action": "ability_detail", "session_id": "...", "ability_name": "Frost Arrow"}
    """
    payload = _safe_dict(data)
    action = _safe_str(payload.get("action")).strip()

    if action == "new_game":
        from app.apps.rpg.session.new_game import RpgNewGameRequest, create_new_game_session

        request = RpgNewGameRequest.model_validate(payload.get("request") or payload)
        return create_new_game_session(request)

    if action == "start_preset":
        from app.apps.rpg.session.new_game import start_rpg_preset

        preset_id = _safe_str(payload.get("preset_id")).strip()
        return start_rpg_preset(preset_id)

    if action == "continue":
        from app.apps.rpg.session.new_game import continue_rpg_session

        session_id = _safe_str(payload.get("session_id")).strip()
        if not session_id:
            return {"ok": False, "error": "missing_session_id"}
        return continue_rpg_session(session_id)

    if action == "rename":
        from app.apps.rpg.session.new_game import rename_rpg_session

        session_id = _safe_str(payload.get("session_id")).strip()
        name = _safe_str(payload.get("name")).strip()
        if not session_id:
            return {"ok": False, "error": "missing_session_id"}
        if not name:
            return {"ok": False, "error": "missing_session_name", "session_id": session_id}
        return rename_rpg_session(session_id, name)

    if action == "delete":
        from app.apps.rpg.session.new_game import delete_rpg_session

        session_id = _safe_str(payload.get("session_id")).strip()
        if not session_id:
            return {"ok": False, "error": "missing_session_id"}
        return delete_rpg_session(session_id)

    if action == "ability_detail":
        from app.apps.rpg.session.ability_detail import generate_ability_detail

        session_id = _safe_str(payload.get("session_id")).strip()
        if not session_id:
            return {"ok": False, "error": "missing_session_id"}
        session, state = _load_mutable_session(session_id)
        if not session:
            return {"ok": False, "error": "session_not_found", "session_id": session_id}
        ability_name = _safe_str(payload.get("ability_name") or payload.get("ability_id")).strip()
        if not ability_name:
            return {"ok": False, "error": "missing_ability_name", "session_id": session_id}
        result = generate_ability_detail(
            state,
            ability_name,
            genre=_safe_str(payload.get("genre")).strip() or None,
        )
        return {"session_id": session_id, **result}

    session_id = _safe_str(payload.get("session_id")).strip()
    if not session_id:
        return {"ok": False, "error": "missing_session_id"}

    from app.apps.rpg.session.action_execution import (
        build_frontend_bootstrap_payload as build_frontend_bootstrap_payload,
    )
    from app.apps.rpg.session.session_runtime_store import (
        load_runtime_session as load_runtime_session,
    )

    session = load_runtime_session(session_id)
    if not session:
        return {"ok": False, "error": "session_not_found", "session_id": session_id}
    game = _safe_dict(build_frontend_bootstrap_payload(session))
    game["session_id"] = session_id
    return {"ok": True, "game": game}
