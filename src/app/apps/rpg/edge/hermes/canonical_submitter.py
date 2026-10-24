from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

Loader = Callable[[str], Any]
Executor = Callable[[Any, str], Any]


def _default_loader(session_id: str) -> Any:
    from app.apps.rpg.session.service import load_session

    return load_session(session_id)


def _default_executor(session: Any, command_text: str, *, submission_id: str = "") -> Any:
    """The turn as the play screen submits it (RQ-1.6): committed like any turn, its result the TurnOutcome."""
    session_data = _to_dict(session)
    manifest = _to_dict(session_data.get("manifest"))
    session_id = str(
        manifest.get("session_id")
        or manifest.get("id")
        or session_data.get("session_id")
        or session_data.get("id")
        or ""
    ).strip()
    if not session_id:
        return {"ok": False, "error": "missing_session_id"}

    from app.apps.rpg.edge.api.turn_pipeline import submit_rpg_turn

    return submit_rpg_turn(
        session_id=session_id,
        command=command_text,
        submission_id=submission_id or f"hermes:{uuid.uuid4().hex}",
        source="hermes",
    )


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
        if error is None and result.get("ok") is False:
            error = result.get("reason") or "turn_failed"
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
    submission_id = str(payload.get("submission_id") or "").strip()

    def default_execute(session: Any, text: str) -> Any:
        return _default_executor(session, text, submission_id=submission_id)

    execute = executor or default_execute
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
    result_data = _to_dict(result)
    nested_result = _to_dict(result_data.get("result"))
    session_data = _to_dict(session)
    simulation_state = _to_dict(session_data.get("simulation_state"))
    player = _to_dict(
        simulation_state.get("player_state")
        or session_data.get("player")
        or getattr(session, "player", None)
    )
    choices = result_data.get("choices") or nested_result.get("choices") or getattr(result, "choices", None)
    dice_roll = result_data.get("dice_roll") or nested_result.get("dice_roll") or getattr(result, "dice_roll", None)
    fail_state = result_data.get("fail_state") or nested_result.get("fail_state") or getattr(result, "fail_state", None)
    narration = result_data.get("narration") or nested_result.get("narration") or getattr(result, "narration", "")
    events = result_data.get("events") or nested_result.get("events") or getattr(result, "events", [])
    turn = result_data.get("turn") or result_data.get("turn_id") or nested_result.get("turn") or getattr(session, "turn_count", None)
    state_changed = result_data.get("state_changed")
    if not isinstance(state_changed, bool):
        state_changed = ok
    outcome = _to_dict(result_data.get("outcome"))
    state_changes = result_data.get("state_changes") or nested_result.get("state_changes") or {}
    if outcome:
        # A turn submitted like the play screen's reports its TurnOutcome (RQ-1.6): what it changed, and the
        # narration the player sees; the hero is read as the turn left them.
        narration = _to_dict(result_data.get("visible_response")).get("plain_text") or result_data.get("response") or narration
        state_changed = _to_dict(result_data.get("state")).get("changed") is True
        state_changes = {"applied_changes": list(outcome.get("applied_changes") or ())}
        turn = outcome.get("turn_id") or turn
        after = _to_dict(load(session_id))
        player = _to_dict(_to_dict(after.get("simulation_state")).get("player_state")) or player

    response: dict[str, Any] = {
        "ok": ok,
        "success": ok,
        "source": "hermes_rpg_canonical_submitter",
        "session_id": session_id,
        "command_text": command_text,
        "turn": turn,
        "narration": narration,
        "state_changes": state_changes,
        "events": _events_to_dicts(events),
        "player": player,
        "state_changed": state_changed,
    }
    if outcome:
        response["outcome"] = outcome
        response["submission_id"] = result_data.get("submission_id") or submission_id
    if choices:
        response["choices"] = choices
    if dice_roll:
        response["dice_roll"] = dice_roll
    if fail_state:
        response["fail_state"] = fail_state
    if error:
        response["error"] = error
    return response
