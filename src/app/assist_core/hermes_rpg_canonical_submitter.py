from __future__ import annotations

from collections.abc import Callable
from typing import Any

Loader = Callable[[str], Any]
Executor = Callable[[Any, str], Any]


def _default_loader(session_id: str) -> Any:
    from app.rpg.pipeline import load_game

    return load_game(session_id)


def _default_executor(session: Any, command_text: str) -> Any:
    from app.rpg.pipeline import execute_turn

    return execute_turn(session, command_text)


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "to_dict"):
        mapped = value.to_dict()
        return dict(mapped) if isinstance(mapped, dict) else {}
    return {}


def _events_to_dicts(events: Any) -> list[dict[str, Any]]:
    if not isinstance(events, list):
        return []
    return [_to_dict(event) for event in events]


def _result_error(result: Any) -> str | None:
    if isinstance(result, dict):
        error = result.get("error")
    else:
        error = getattr(result, "error", None)
    return str(error) if error else None


def hermes_rpg_canonical_submitter(
    payload: dict[str, Any],
    *,
    loader: Loader | None = None,
    executor: Executor | None = None,
) -> dict[str, Any]:
    """Submit an approved Hermes RPG command through the canonical RPG turn path."""
    session_id = str(payload.get("session_id") or "").strip()
    command_text = str(payload.get("command_text") or payload.get("input") or "").strip()
    if not session_id:
        return {
            "ok": False,
            "success": False,
            "source": "hermes_rpg_canonical_submitter",
            "error": "missing_session_id",
            "state_changed": False,
        }
    if not command_text:
        return {
            "ok": False,
            "success": False,
            "source": "hermes_rpg_canonical_submitter",
            "session_id": session_id,
            "error": "missing_command",
            "state_changed": False,
        }

    load = loader or _default_loader
    execute = executor or _default_executor
    session = load(session_id)
    if not session:
        return {
            "ok": False,
            "success": False,
            "source": "hermes_rpg_canonical_submitter",
            "session_id": session_id,
            "command_text": command_text,
            "error": "game_not_found",
            "state_changed": False,
        }

    result = execute(session, command_text)
    error = _result_error(result)
    ok = error is None
    player = _to_dict(getattr(session, "player", None))
    choices = getattr(result, "choices", None) if not isinstance(result, dict) else result.get("choices")
    dice_roll = getattr(result, "dice_roll", None) if not isinstance(result, dict) else result.get("dice_roll")
    fail_state = getattr(result, "fail_state", None) if not isinstance(result, dict) else result.get("fail_state")

    response: dict[str, Any] = {
        "ok": ok,
        "success": ok,
        "source": "hermes_rpg_canonical_submitter",
        "session_id": session_id,
        "command_text": command_text,
        "turn": getattr(session, "turn_count", None),
        "narration": getattr(result, "narration", "") if not isinstance(result, dict) else result.get("narration", ""),
        "state_changes": getattr(result, "state_changes", {}) if not isinstance(result, dict) else result.get("state_changes", {}),
        "events": _events_to_dicts(getattr(result, "events", []) if not isinstance(result, dict) else result.get("events", [])),
        "player": player,
        "state_changed": ok,
    }
    if choices:
        response["choices"] = choices
    if dice_roll:
        response["dice_roll"] = dice_roll
    if fail_state:
        response["fail_state"] = fail_state
    if error:
        response["error"] = error
    return response
