"""Runtime-safe travel state enrichment for interactive RPG feature runs."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from app.rpg.interactive_cli_travel_state import (
    TRAVEL_STATE_PATCH,
    TRAVEL_STATE_SOURCE,
    advance_travel_state,
    travel_requested_terms_for_state,
)


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _is_travel_command(command: str, turn: Mapping[str, Any]) -> bool:
    text = command.lower()
    if any(term in text for term in ("travel", "leave", "road", "north", "south", "old mill", "mill", "head back", "go back", "look around")):
        return True
    diagnostics = _safe_dict(turn.get("interactive_cli_intent_diagnostics"))
    final = _safe_dict(diagnostics.get("final_classification"))
    return _safe_str(final.get("action_type")).lower() == "travel"


def _set_travel_state_on_turn(turn: Mapping[str, Any], *, command: str, previous_state: Mapping[str, Any] | None) -> dict[str, Any]:
    out = deepcopy(_safe_dict(turn))
    state = advance_travel_state(previous_state, command)
    out["interactive_cli_travel_state"] = state

    raw_result = deepcopy(_safe_dict(out.get("raw_result") or out.get("result")))
    raw_result["interactive_cli_travel_state"] = state
    raw_result["travel_state_source"] = TRAVEL_STATE_SOURCE
    raw_result["travel_state_patch"] = TRAVEL_STATE_PATCH

    diagnostics = deepcopy(
        _safe_dict(out.get("interactive_cli_intent_diagnostics") or raw_result.get("interactive_cli_intent_diagnostics"))
    )
    final = deepcopy(_safe_dict(diagnostics.get("final_classification")))
    final["action_type"] = "travel"
    final["current_location_id"] = state["current_location_id"]
    final["current_location_name"] = state["current_location_name"]
    final["destination_id"] = state["destination_id"]
    final["destination_name"] = state["destination_name"]
    final["direction"] = state["direction"]
    final["requested_terms"] = travel_requested_terms_for_state(
        state,
        command,
        _safe_list(final.get("requested_terms")),
    )
    diagnostics["final_classification"] = final
    diagnostics["travel_state_source"] = TRAVEL_STATE_SOURCE
    diagnostics["travel_state_patch"] = TRAVEL_STATE_PATCH
    raw_result["interactive_cli_intent_diagnostics"] = diagnostics

    out["raw_result"] = raw_result
    out["result"] = raw_result
    out["interactive_cli_intent_diagnostics"] = diagnostics
    out["travel_state_source"] = TRAVEL_STATE_SOURCE
    out["travel_state_patch"] = TRAVEL_STATE_PATCH
    return out


def apply_travel_state_to_matrix_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """Attach deterministic same-scenario travel state to matrix turns."""

    result_dict = _safe_dict(result)
    changed = 0
    scenarios: list[dict[str, Any]] = []
    for item in _safe_list(result_dict.get("results")):
        scenario = item.get("scenario")
        scenario_id = _safe_str(getattr(scenario, "scenario_id", "") or _safe_dict(scenario).get("scenario_id"))
        commands = list(getattr(scenario, "commands", ()) or _safe_dict(scenario).get("commands") or ())
        scenario_result = _safe_dict(item.get("result"))
        turns = []
        previous_state: Mapping[str, Any] | None = None
        scenario_changed = 0
        for index, turn in enumerate(_safe_list(scenario_result.get("turns"))):
            turn_dict = _safe_dict(turn)
            command = _safe_str(
                turn_dict.get("player_input")
                or turn_dict.get("player_action")
                or (commands[index] if index < len(commands) else "")
            )
            if _is_travel_command(command, turn_dict):
                cleaned = _set_travel_state_on_turn(turn_dict, command=command, previous_state=previous_state)
                previous_state = _safe_dict(cleaned.get("interactive_cli_travel_state"))
                scenario_changed += 1
                turns.append(cleaned)
            else:
                turns.append(turn_dict)
        scenario_result["turns"] = turns
        item["result"] = scenario_result
        changed += scenario_changed
        scenarios.append({"scenario_id": scenario_id, "changed_turns": scenario_changed})
    return {
        "ok": True,
        "source": TRAVEL_STATE_SOURCE,
        "patch": TRAVEL_STATE_PATCH,
        "changed_turns": changed,
        "scenarios": scenarios,
    }
