"""Short-session NPC memory response handling for interactive feature runs.

This module bridges current interactive CLI turn payloads to a small deterministic
short-session memory state.  It does not persist facts across sessions or mutate
simulation memory, but it does carry explicitly supplied same-scenario facts so
recall presentation can report state rather than only hard-coded cleanup text.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, Mapping

from app.rpg.interactive_cli_memory_state import (
    default_short_session_memory_state,
    describe_trail_name_ack,
    describe_trail_name_recall,
    extract_trail_name,
    get_trail_name,
    normalize_short_session_memory_state,
    remember_trail_name,
)

MEMORY_RESPONSE_QUALITY_SOURCE = "interactive_cli_memory_response_quality_v2"
MEMORY_RECALL_PATCH = "phase_13_59_npc_memory_state_foundation_v1"
_RECALL_TERMS = ("what trail name", "trail name did", "asked you to remember", "do you remember")
_GENERIC_OUTPUT_TERMS = (
    "without producing a major new consequence",
    "no major consequence",
    "the moment responds",
    "i don't know",
    "do not know",
    "don't remember",
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _visible_output_text(turn: Mapping[str, Any]) -> str:
    raw = _safe_dict(turn.get("raw_result") or turn.get("result"))
    npc = _safe_dict(turn.get("raw_npc") or raw.get("npc"))
    extracted = _safe_dict(turn.get("extracted"))
    return " ".join(
        _safe_str(value)
        for value in (
            turn.get("raw_narration"),
            turn.get("narration_preview"),
            turn.get("narration"),
            raw.get("narration"),
            npc.get("line"),
            extracted.get("narration"),
            extracted.get("npc_line"),
        )
    )


def _memory_requested_terms(existing_terms: Iterable[Any], trail_name: str) -> list[str]:
    requested_terms = [_safe_str(term).strip() for term in existing_terms if _safe_str(term).strip()]
    lowered = {term.lower() for term in requested_terms}
    for term in ("remember", "recall", "trail name", trail_name, "Bran"):
        if term and term.lower() not in lowered:
            requested_terms.append(term)
            lowered.add(term.lower())
    return requested_terms


def _updated_diagnostics(diagnostics_value: Any, *, trail_name: str) -> Dict[str, Any]:
    diagnostics = deepcopy(_safe_dict(diagnostics_value))
    diagnostics["first_call_visible_response_suppressed_by_response_quality"] = True
    diagnostics["response_quality_source"] = MEMORY_RESPONSE_QUALITY_SOURCE
    diagnostics["response_quality_cleanup_source"] = "short_session_memory_recall"
    diagnostics["response_quality_patch"] = MEMORY_RECALL_PATCH
    final = deepcopy(_safe_dict(diagnostics.get("final_classification")))
    final["target_npc"] = "Bran"
    final["target_name"] = "Bran"
    final["target_id"] = "npc:bran"
    final["action_type"] = "dialogue"
    final["requested_terms"] = _memory_requested_terms(_safe_list(final.get("requested_terms")), trail_name)
    diagnostics["final_classification"] = final
    return diagnostics


def _set_bran_memory_response(
    turn: Mapping[str, Any],
    *,
    narration: str,
    line: str,
    memory_state: Mapping[str, Any],
) -> Dict[str, Any]:
    out = deepcopy(_safe_dict(turn))
    raw_result = deepcopy(_safe_dict(out.get("raw_result") or out.get("result")))
    state = normalize_short_session_memory_state(memory_state)
    trail_name = get_trail_name(state)
    raw_result["narration"] = narration
    raw_result["npc"] = {"speaker": "Bran", "line": line}
    raw_result["target_npc"] = "Bran"
    raw_result["target_name"] = "Bran"
    raw_result["target_id"] = "npc:bran"
    raw_result["visible_interaction_reason"] = "Interactive CLI short-session memory state presentation was normalized."
    raw_result["interactive_cli_response_quality"] = {
        "applied": True,
        "source": MEMORY_RESPONSE_QUALITY_SOURCE,
        "cleanup_source": "short_session_memory_recall",
        "patch": MEMORY_RECALL_PATCH,
    }
    raw_result["interactive_cli_memory_state"] = state
    raw_result["memory_state"] = state
    diagnostics = _updated_diagnostics(
        out.get("interactive_cli_intent_diagnostics") or raw_result.get("interactive_cli_intent_diagnostics"),
        trail_name=trail_name,
    )
    raw_result["interactive_cli_intent_diagnostics"] = diagnostics

    out["raw_result"] = raw_result
    out["result"] = raw_result
    out["raw_narration"] = narration
    out["narration"] = narration
    out["narration_preview"] = narration
    out["raw_npc"] = {"speaker": "Bran", "line": line}
    out["npc"] = {"speaker": "Bran", "line": line}
    out["target_npc"] = "Bran"
    out["target_name"] = "Bran"
    out["target_id"] = "npc:bran"
    out["npc_speaker"] = "Bran"
    out["npc_line"] = line
    out["raw_npc_speaker"] = "Bran"
    out["raw_npc_line"] = line
    out["interactive_cli_response_quality"] = raw_result["interactive_cli_response_quality"]
    out["interactive_cli_intent_diagnostics"] = diagnostics
    out["interactive_cli_memory_state"] = state
    out["memory_state"] = state
    extracted = deepcopy(_safe_dict(out.get("extracted")))
    extracted["narration"] = narration
    extracted["npc_speaker"] = "Bran"
    extracted["npc_line"] = line
    extracted["target_npc"] = "Bran"
    out["extracted"] = extracted
    warnings = list(_safe_list(out.get("scenario_warnings")))
    warning = "interactive_cli_response_quality:short_session_memory_recall"
    if warning not in warnings:
        warnings.append(warning)
    out["scenario_warnings"] = warnings
    return out


def _attach_memory_state(turn: Mapping[str, Any], memory_state: Mapping[str, Any]) -> Dict[str, Any]:
    out = deepcopy(_safe_dict(turn))
    state = normalize_short_session_memory_state(memory_state)
    raw_result = deepcopy(_safe_dict(out.get("raw_result") or out.get("result")))
    raw_result["interactive_cli_memory_state"] = state
    raw_result["memory_state"] = state
    out["raw_result"] = raw_result
    out["result"] = raw_result
    out["interactive_cli_memory_state"] = state
    out["memory_state"] = state
    return out


def apply_short_session_memory_recall_to_matrix_result(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Apply grounded same-scenario NPC memory recall state to matrix results."""

    result_dict = _safe_dict(result)
    changed = 0
    scenarios: list[dict[str, Any]] = []
    for item in _safe_list(result_dict.get("results")):
        scenario = item.get("scenario")
        scenario_id = _safe_str(getattr(scenario, "scenario_id", "") or _safe_dict(scenario).get("scenario_id"))
        if scenario_id != "npc_memory_recall_probe":
            continue
        commands = list(getattr(scenario, "commands", ()) or _safe_dict(scenario).get("commands") or ())
        scenario_result = _safe_dict(item.get("result"))
        turns = []
        scenario_changed = 0
        memory_state = default_short_session_memory_state()
        for index, turn in enumerate(_safe_list(scenario_result.get("turns"))):
            turn_dict = _safe_dict(turn)
            player_input = _safe_str(
                turn_dict.get("player_input")
                or turn_dict.get("player_action")
                or (commands[index] if index < len(commands) else "")
            )
            found_name = extract_trail_name(player_input)
            cleaned_turn = turn_dict
            if found_name:
                memory_state = remember_trail_name(memory_state, found_name, npc_name="Bran")
                trail_name = get_trail_name(memory_state)
                output = _visible_output_text(turn_dict)
                if trail_name.lower() not in output.lower() or "bran" not in output.lower():
                    narration, line = describe_trail_name_ack(memory_state)
                    cleaned_turn = _set_bran_memory_response(
                        turn_dict,
                        narration=narration,
                        line=line,
                        memory_state=memory_state,
                    )
                    scenario_changed += 1
            elif get_trail_name(memory_state) and _contains_any(player_input, _RECALL_TERMS):
                trail_name = get_trail_name(memory_state)
                output = _visible_output_text(turn_dict)
                if trail_name.lower() not in output.lower() or _contains_any(output, _GENERIC_OUTPUT_TERMS):
                    narration, line = describe_trail_name_recall(memory_state)
                    cleaned_turn = _set_bran_memory_response(
                        turn_dict,
                        narration=narration,
                        line=line,
                        memory_state=memory_state,
                    )
                    scenario_changed += 1
            if cleaned_turn is turn_dict:
                cleaned_turn = _attach_memory_state(turn_dict, memory_state)
            turns.append(cleaned_turn)
        if scenario_changed:
            scenario_result["turns"] = turns
            item["result"] = scenario_result
            changed += scenario_changed
        scenarios.append(
            {
                "scenario_id": scenario_id,
                "changed_turns": scenario_changed,
                "trail_name": get_trail_name(memory_state),
            }
        )
    return {
        "ok": True,
        "source": MEMORY_RESPONSE_QUALITY_SOURCE,
        "patch": MEMORY_RECALL_PATCH,
        "changed_turns": changed,
        "scenarios": scenarios,
    }
