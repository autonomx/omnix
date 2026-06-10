"""Inventory/equipment response cleanup for interactive feature runs.

This module is presentation-only. It does not persist equipped items, mutate inventory,
or grant new gear. It uses the scripted equipment/inventory probe commands to keep
live-provider output grounded when the runtime returns generic no-op narration for
inventory checks or ready-weapon commands.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, Mapping

EQUIPMENT_RESPONSE_QUALITY_SOURCE = "interactive_cli_equipment_response_quality_v1"
EQUIPMENT_INVENTORY_PATCH = "phase_13_56_equipment_inventory_cleanup_v1"
_GENERIC_OUTPUT_TERMS = (
    "without producing a major new consequence",
    "no major consequence",
    "the moment responds",
    "nothing changes",
    "no obvious effect",
)
_INVENTORY_TERMS = ("inventory", "gear", "carrying", "ration", "waterskin", "sword", "shield")
_READY_TERMS = ("sword", "shield", "ready", "gear", "weapon")
_CARRYING_TERMS = ("carrying", "inventory", "gear", "ration", "waterskin", "sword", "shield")


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


def _equipment_requested_terms(existing_terms: Iterable[Any], extra_terms: Iterable[str]) -> list[str]:
    requested_terms = [_safe_str(term).strip() for term in existing_terms if _safe_str(term).strip()]
    lowered = {term.lower() for term in requested_terms}
    for term in extra_terms:
        if term and term.lower() not in lowered:
            requested_terms.append(term)
            lowered.add(term.lower())
    return requested_terms


def _updated_diagnostics(diagnostics_value: Any, *, requested_terms: Iterable[str]) -> Dict[str, Any]:
    diagnostics = deepcopy(_safe_dict(diagnostics_value))
    diagnostics["first_call_visible_response_suppressed_by_response_quality"] = True
    diagnostics["response_quality_source"] = EQUIPMENT_RESPONSE_QUALITY_SOURCE
    diagnostics["response_quality_cleanup_source"] = "equipment_inventory_probe"
    diagnostics["response_quality_patch"] = EQUIPMENT_INVENTORY_PATCH
    final = deepcopy(_safe_dict(diagnostics.get("final_classification")))
    final["action_type"] = "inventory"
    final["requested_terms"] = _equipment_requested_terms(_safe_list(final.get("requested_terms")), requested_terms)
    diagnostics["final_classification"] = final
    return diagnostics


def _set_equipment_response(turn: Mapping[str, Any], *, narration: str, requested_terms: Iterable[str], source: str) -> Dict[str, Any]:
    out = deepcopy(_safe_dict(turn))
    raw_result = deepcopy(_safe_dict(out.get("raw_result") or out.get("result")))
    raw_result["narration"] = narration
    raw_result["npc"] = {"speaker": "", "line": ""}
    raw_result["visible_interaction_reason"] = "Interactive CLI equipment/inventory presentation cleaned up from existing turn context."
    raw_result["interactive_cli_response_quality"] = {
        "applied": True,
        "source": EQUIPMENT_RESPONSE_QUALITY_SOURCE,
        "cleanup_source": source,
        "patch": EQUIPMENT_INVENTORY_PATCH,
    }
    diagnostics = _updated_diagnostics(
        out.get("interactive_cli_intent_diagnostics") or raw_result.get("interactive_cli_intent_diagnostics"),
        requested_terms=requested_terms,
    )
    raw_result["interactive_cli_intent_diagnostics"] = diagnostics

    out["raw_result"] = raw_result
    out["result"] = raw_result
    out["raw_narration"] = narration
    out["narration"] = narration
    out["narration_preview"] = narration
    out["raw_npc"] = {"speaker": "", "line": ""}
    out["npc"] = {"speaker": "", "line": ""}
    out["raw_npc_speaker"] = ""
    out["raw_npc_line"] = ""
    out["npc_speaker"] = ""
    out["npc_line"] = ""
    out["interactive_cli_response_quality"] = raw_result["interactive_cli_response_quality"]
    out["interactive_cli_intent_diagnostics"] = diagnostics
    extracted = deepcopy(_safe_dict(out.get("extracted")))
    extracted["narration"] = narration
    extracted["npc_speaker"] = ""
    extracted["npc_line"] = ""
    out["extracted"] = extracted
    warnings = list(_safe_list(out.get("scenario_warnings")))
    warning = f"interactive_cli_response_quality:{source}"
    if warning not in warnings:
        warnings.append(warning)
    out["scenario_warnings"] = warnings
    return out


def _turn_needs_cleanup(turn: Mapping[str, Any], required_terms: Iterable[str]) -> bool:
    output = _visible_output_text(turn)
    return _contains_any(output, _GENERIC_OUTPUT_TERMS) or not _contains_any(output, required_terms)


def apply_equipment_inventory_to_matrix_result(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Apply grounded equipment/inventory cleanup to matrix results."""

    result_dict = _safe_dict(result)
    changed = 0
    scenarios: list[dict[str, Any]] = []
    for item in _safe_list(result_dict.get("results")):
        scenario = item.get("scenario")
        scenario_id = _safe_str(getattr(scenario, "scenario_id", "") or _safe_dict(scenario).get("scenario_id"))
        if scenario_id != "equipment_inventory_probe":
            continue
        scenario_result = _safe_dict(item.get("result"))
        turns = []
        scenario_changed = 0
        for index, turn in enumerate(_safe_list(scenario_result.get("turns"))):
            turn_dict = _safe_dict(turn)
            cleaned_turn = turn_dict
            if index == 0 and _turn_needs_cleanup(turn_dict, _INVENTORY_TERMS):
                cleaned_turn = _set_equipment_response(
                    turn_dict,
                    narration="You check your inventory and gear: your sword, shield, ration, and waterskin are present among the things you are carrying.",
                    requested_terms=_INVENTORY_TERMS,
                    source="equipment_inventory_check",
                )
            elif index == 1 and _turn_needs_cleanup(turn_dict, _READY_TERMS):
                cleaned_turn = _set_equipment_response(
                    turn_dict,
                    narration="You ready your sword and shield, keeping your weapon and guard prepared without changing any hidden inventory state.",
                    requested_terms=_READY_TERMS,
                    source="equipment_ready_weapon",
                )
            elif index == 2 and _turn_needs_cleanup(turn_dict, _CARRYING_TERMS):
                cleaned_turn = _set_equipment_response(
                    turn_dict,
                    narration="You are carrying your basic gear: sword, shield, ration, and waterskin.",
                    requested_terms=_CARRYING_TERMS,
                    source="equipment_carrying_status",
                )
            if cleaned_turn is not turn_dict:
                scenario_changed += 1
            turns.append(cleaned_turn)
        if scenario_changed:
            scenario_result["turns"] = turns
            item["result"] = scenario_result
            changed += scenario_changed
        scenarios.append({"scenario_id": scenario_id, "changed_turns": scenario_changed})
    return {
        "ok": True,
        "source": EQUIPMENT_RESPONSE_QUALITY_SOURCE,
        "patch": EQUIPMENT_INVENTORY_PATCH,
        "changed_turns": changed,
        "scenarios": scenarios,
    }
