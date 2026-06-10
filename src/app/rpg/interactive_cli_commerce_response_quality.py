"""Interactive CLI commerce response/state enrichment.

This pass is runtime-safe for review artifacts: it records unsupported sell attempts
as explicit commerce state and keeps presentation grounded in that state without
mutating authoritative inventory or currency.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Mapping

from app.rpg.interactive_cli_commerce_state import (
    apply_sell_attempt,
    default_commerce_state,
    describe_sell_attempt,
    extract_commerce_state,
    is_sell_request,
)

COMMERCE_RESPONSE_QUALITY_SOURCE = "interactive_cli_commerce_response_quality_v1"
COMMERCE_RESPONSE_QUALITY_PATCH = "phase_13_61_commerce_sell_state_foundation_v1"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _final_intent(turn: Mapping[str, Any]) -> Dict[str, Any]:
    diagnostics = _safe_dict(turn.get("interactive_cli_intent_diagnostics"))
    if not diagnostics:
        raw = _safe_dict(turn.get("raw_result") or turn.get("result"))
        diagnostics = _safe_dict(raw.get("interactive_cli_intent_diagnostics"))
    return _safe_dict(diagnostics.get("final_classification"))


def _commerce_requested_terms(existing_terms: Any) -> list[str]:
    terms = [_safe_str(term).strip() for term in _safe_list(existing_terms) if _safe_str(term).strip()]
    lowered = {term.lower() for term in terms}
    for term in ("sell", "ration", "trade", "copper", "Bran"):
        if term.lower() not in lowered:
            terms.append(term)
            lowered.add(term.lower())
    return terms


def _updated_commerce_diagnostics(diagnostics_value: Any) -> Dict[str, Any]:
    diagnostics = deepcopy(_safe_dict(diagnostics_value))
    diagnostics["commerce_response_quality_source"] = COMMERCE_RESPONSE_QUALITY_SOURCE
    diagnostics["commerce_response_quality_patch"] = COMMERCE_RESPONSE_QUALITY_PATCH
    final = deepcopy(_safe_dict(diagnostics.get("final_classification")))
    final["action_type"] = "economy"
    final["service_kind"] = "trade"
    final["target_npc"] = "Bran"
    final["target_name"] = "Bran"
    final["target_id"] = "npc:bran"
    final["requested_terms"] = _commerce_requested_terms(final.get("requested_terms"))
    diagnostics["final_classification"] = final
    return diagnostics


def _set_commerce_state_response(turn: Mapping[str, Any], *, commerce_state: Mapping[str, Any]) -> Dict[str, Any]:
    out = deepcopy(_safe_dict(turn))
    raw_result = deepcopy(_safe_dict(out.get("raw_result") or out.get("result")))
    narration, line = describe_sell_attempt(commerce_state)
    raw_result["narration"] = narration
    raw_result["npc"] = {"speaker": "Bran", "line": line}
    raw_result["target_npc"] = "Bran"
    raw_result["target_name"] = "Bran"
    raw_result["target_id"] = "npc:bran"
    raw_result["interactive_cli_commerce_state"] = deepcopy(dict(commerce_state))
    raw_result["commerce_state"] = deepcopy(dict(commerce_state))
    raw_result["interactive_cli_commerce_response_quality"] = {
        "applied": True,
        "source": COMMERCE_RESPONSE_QUALITY_SOURCE,
        "patch": COMMERCE_RESPONSE_QUALITY_PATCH,
    }

    diagnostics = _updated_commerce_diagnostics(
        out.get("interactive_cli_intent_diagnostics") or raw_result.get("interactive_cli_intent_diagnostics")
    )
    raw_result["interactive_cli_intent_diagnostics"] = diagnostics

    out["raw_result"] = raw_result
    out["result"] = raw_result
    out["raw_narration"] = narration
    out["narration"] = narration
    out["narration_preview"] = narration
    out["raw_npc"] = {"speaker": "Bran", "line": line}
    out["npc"] = {"speaker": "Bran", "line": line}
    out["raw_npc_speaker"] = "Bran"
    out["raw_npc_line"] = line
    out["npc_speaker"] = "Bran"
    out["npc_line"] = line
    out["target_npc"] = "Bran"
    out["target_name"] = "Bran"
    out["target_id"] = "npc:bran"
    out["interactive_cli_commerce_state"] = deepcopy(dict(commerce_state))
    out["commerce_state"] = deepcopy(dict(commerce_state))
    out["interactive_cli_commerce_response_quality"] = raw_result["interactive_cli_commerce_response_quality"]
    out["interactive_cli_intent_diagnostics"] = diagnostics

    extracted = deepcopy(_safe_dict(out.get("extracted")))
    extracted["narration"] = narration
    extracted["npc_speaker"] = "Bran"
    extracted["npc_line"] = line
    extracted["target_npc"] = "Bran"
    out["extracted"] = extracted
    return out


def apply_commerce_sell_state_cleanup(
    turn_summary: Mapping[str, Any],
    *,
    player_input: str,
    previous_state: Mapping[str, Any] | None = None,
    turn_index: int = 0,
) -> Dict[str, Any]:
    """Apply commerce sell state to a single turn when the command is a sell request."""

    out = deepcopy(_safe_dict(turn_summary))
    intent = _final_intent(out)
    if not is_sell_request(player_input, intent.get("requested_terms") or ()):  # not a commerce sell/value probe
        if previous_state is not None:
            state = dict(previous_state)
            out["interactive_cli_commerce_state"] = deepcopy(state)
            raw_result = deepcopy(_safe_dict(out.get("raw_result") or out.get("result")))
            raw_result["interactive_cli_commerce_state"] = deepcopy(state)
            out["raw_result"] = raw_result
            out["result"] = raw_result
        return out

    state = extract_commerce_state(out if previous_state is None else {"interactive_cli_commerce_state": previous_state})
    next_state = apply_sell_attempt(state, player_input=player_input, turn_index=turn_index)
    return _set_commerce_state_response(out, commerce_state=next_state)


def apply_commerce_sell_state_to_matrix_result(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Apply short-session commerce sell state to all matrix turns."""

    result_dict = _safe_dict(result)
    changed = 0
    scenarios = []
    for item in _safe_list(result_dict.get("results")):
        scenario = item.get("scenario")
        scenario_id = _safe_str(getattr(scenario, "scenario_id", "") or _safe_dict(scenario).get("scenario_id"))
        commands = list(getattr(scenario, "commands", ()) or _safe_dict(scenario).get("commands") or ())
        scenario_result = _safe_dict(item.get("result"))
        turns = []
        scenario_changed = 0
        commerce_state = default_commerce_state()
        for index, turn in enumerate(_safe_list(scenario_result.get("turns"))):
            turn_dict = _safe_dict(turn)
            player_input = _safe_str(
                turn_dict.get("player_input")
                or turn_dict.get("player_action")
                or (commands[index] if index < len(commands) else "")
            )
            cleaned = apply_commerce_sell_state_cleanup(
                turn_dict,
                player_input=player_input,
                previous_state=commerce_state,
                turn_index=index + 1,
            )
            next_state = extract_commerce_state(cleaned)
            if _safe_dict(cleaned).get("interactive_cli_commerce_response_quality"):
                scenario_changed += 1
            commerce_state = next_state
            turns.append(cleaned)
        scenario_result["turns"] = turns
        item["result"] = scenario_result
        changed += scenario_changed
        scenarios.append({"scenario_id": scenario_id, "changed_turns": scenario_changed})
    return {
        "ok": True,
        "source": COMMERCE_RESPONSE_QUALITY_SOURCE,
        "patch": COMMERCE_RESPONSE_QUALITY_PATCH,
        "changed_turns": changed,
        "scenarios": scenarios,
    }
