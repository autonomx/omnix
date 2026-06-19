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


def _safe_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _safe_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_mutable_session(session_id: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    from app.rpg.session.service import load_session

    session = load_session(session_id)
    if not session:
        return None, {}
    state = _safe_dict(session.get("state"))
    session["state"] = state
    return session, state


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
    """Return a session envelope or perform a synchronous RPG action.

    This gateway-compat route is used by the web app while typed RPG endpoints
    are being promoted. Supported actions are synchronous and do not call
    LLM/image/TTS services:

    - {"action": "new_game", ...}
    - {"action": "start_preset", "preset_id": "demo_glimmerdeep_pass_lvl14"}
    - {"action": "continue", "session_id": "..."}
    - {"action": "rename", "session_id": "...", "name": "..."}
    - {"action": "delete", "session_id": "..."}
    - {"action": "loadout_action", "session_id": "...", "loadout": {...}}
    - {"action": "item_command", "session_id": "...", "command": "item report"}
    - {"action": "item_diagnostics", "session_id": "...", "record": true}
    - {"action": "item_maintenance", "session_id": "...", "dry_run": true}
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

    if action == "rename":
        from app.rpg.session.new_game import rename_rpg_session

        session_id = _safe_str(payload.get("session_id")).strip()
        name = _safe_str(payload.get("name")).strip()
        if not session_id:
            return {"ok": False, "error": "missing_session_id"}
        if not name:
            return {"ok": False, "error": "missing_session_name", "session_id": session_id}
        return rename_rpg_session(session_id, name)

    if action == "delete":
        from app.rpg.session.new_game import delete_rpg_session

        session_id = _safe_str(payload.get("session_id")).strip()
        if not session_id:
            return {"ok": False, "error": "missing_session_id"}
        return delete_rpg_session(session_id)

    if action == "loadout_action":
        from app.rpg.session.loadout import RpgLoadoutActionRequest, apply_loadout_action

        session_id = _safe_str(payload.get("session_id")).strip()
        if not session_id:
            return {"ok": False, "error": "missing_session_id"}
        request = RpgLoadoutActionRequest.model_validate(payload.get("loadout") or payload)
        return apply_loadout_action(session_id, request)

    if action == "item_command":
        from app.rpg.session.item_command_adapter import apply_item_command
        from app.rpg.session.service import save_session

        session_id = _safe_str(payload.get("session_id")).strip()
        if not session_id:
            return {"ok": False, "error": "missing_session_id"}
        session, state = _load_mutable_session(session_id)
        if not session:
            return {"ok": False, "error": "session_not_found", "session_id": session_id}
        command = payload.get("command") if "command" in payload else payload.get("item_command") or payload.get("request")
        result = apply_item_command(state, command)
        if result.get("ok") is not True:
            return {"session_id": session_id, **result}
        saved = save_session(session, compact=False)
        return {
            "ok": True,
            "session_id": session_id,
            "status": "ready",
            "session": saved,
            "game": saved.get("state", {}),
            **result,
        }

    if action == "item_diagnostics":
        from app.rpg.session.item_diagnostics import build_item_diagnostics, record_item_diagnostics
        from app.rpg.session.service import save_session

        session_id = _safe_str(payload.get("session_id")).strip()
        if not session_id:
            return {"ok": False, "error": "missing_session_id"}
        session, state = _load_mutable_session(session_id)
        if not session:
            return {"ok": False, "error": "session_not_found", "session_id": session_id}
        station = _safe_str(payload.get("station")).strip() or None
        genre = _safe_str(payload.get("genre")).strip() or "classic_fantasy"
        scenario_limit = _safe_int(payload.get("scenario_limit"), default=8)
        objective_limit = _safe_int(payload.get("objective_limit"), default=8)
        if _safe_bool(payload.get("record") or payload.get("record_trace")):
            diagnostics = record_item_diagnostics(
                state,
                station=station,
                genre=genre,
                scenario_limit=scenario_limit,
                objective_limit=objective_limit,
            )
            saved = save_session(session, compact=False)
            return {
                "ok": True,
                "session_id": session_id,
                "status": "ready",
                "session": saved,
                "game": saved.get("state", {}),
                "diagnostics": diagnostics,
            }
        diagnostics = build_item_diagnostics(
            state,
            station=station,
            genre=genre,
            scenario_limit=scenario_limit,
            objective_limit=objective_limit,
        )
        return {
            "ok": True,
            "session_id": session_id,
            "status": "ready",
            "game": state,
            "diagnostics": diagnostics,
        }

    if action == "item_maintenance":
        from app.rpg.session.item_state_maintenance import (
            build_item_state_maintenance_plan,
            run_item_state_maintenance,
        )
        from app.rpg.session.service import save_session

        session_id = _safe_str(payload.get("session_id")).strip()
        if not session_id:
            return {"ok": False, "error": "missing_session_id"}
        session, state = _load_mutable_session(session_id)
        if not session:
            return {"ok": False, "error": "session_not_found", "session_id": session_id}
        bucket_limit = _safe_int(payload.get("bucket_limit"), default=50)
        compaction_threshold = _safe_int(payload.get("compaction_threshold"), default=bucket_limit)
        record_report = _safe_bool(payload.get("record_report"), default=False)
        if _safe_bool(payload.get("dry_run"), default=False):
            maintenance = build_item_state_maintenance_plan(
                state,
                bucket_limit=bucket_limit,
                compaction_threshold=compaction_threshold,
                include_report=record_report,
            )
            return {
                "ok": True,
                "session_id": session_id,
                "status": "ready",
                "game": state,
                "maintenance": maintenance,
            }
        maintenance = run_item_state_maintenance(
            state,
            bucket_limit=bucket_limit,
            compaction_threshold=compaction_threshold,
            record_report=record_report,
        )
        saved = save_session(session, compact=False)
        return {
            "ok": maintenance.get("ok") is True,
            "session_id": session_id,
            "status": "ready",
            "session": saved,
            "game": saved.get("state", {}),
            "maintenance": maintenance,
        }

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
