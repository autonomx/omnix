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
    """Return the legacy RPG session list envelope plus launch presets."""
    from app.rpg.session.new_game import list_rpg_presets
    from app.rpg.session.service import list_sessions

    presets_payload = list_rpg_presets()
    return {
        "ok": True,
        "sessions": list_sessions() or [],
        "presets": presets_payload.get("presets", []),
    }


def get_rpg_session_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Return a session envelope or perform a synchronous RPG launch action.

    This gateway-compat route is used by the web app while the typed RPG
    endpoints are being promoted. Supported launch actions are intentionally
    synchronous and do not call LLM/image/TTS services:

    - {"action": "new_game", ...}
    - {"action": "start_preset", "preset_id": "demo_glimmerdeep_pass_lvl14"}
    - {"action": "continue", "session_id": "..."}
    """
    payload = _safe_dict(data)
    action = _safe_str(payload.get("action")).strip()

    if action == "new_game":
        from app.rpg.session.new_game import RpgNewGameRequest, create_new_game_session

        request = RpgNewGameRequest.model_validate(payload.get("request") or payload)
        return create_new_game_session(request)

    if action == "start_preset":
        from app.rpg.session.new_game import start_rpg_preset

        preset_id = _safe_str(payload.get("preset_id")).strip()
        return start_rpg_preset(preset_id)

    if action == "continue":
        from app.rpg.session.new_game import continue_rpg_session

        session_id = _safe_str(payload.get("session_id")).strip()
        if not session_id:
            return {"ok": False, "error": "missing_session_id"}
        return continue_rpg_session(session_id)

    session_id = _safe_str(payload.get("session_id")).strip()
    if not session_id:
        return {"ok": False, "error": "missing_session_id"}

    from app.rpg.session.runtime import build_frontend_bootstrap_payload, load_runtime_session

    session = load_runtime_session(session_id)
    if not session:
        return {"ok": False, "error": "session_not_found", "session_id": session_id}

    game = _safe_dict(build_frontend_bootstrap_payload(session))
    if game.get("session_id") == "session:unknown":
        game["session_id"] = session_id
    return {"ok": True, "game": game}
