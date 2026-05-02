from __future__ import annotations

from typing import Any, Dict, List

from tests.rpg.manual.extractors.narration import (
    _extract_narration_quality_warnings,
    _extract_npc_backbone_decision,
    _runtime_has_narration_quality_memory,
)
from tests.rpg.manual.safe import _safe_str


def validate_narration_n1_n3_turn(
    *,
    scenario_name: str,
    summary_row: Dict[str, Any],
) -> List[str]:
    warnings: List[str] = []

    if scenario_name == "narration_repetition_memory_tracks_recent_output":
        if not _runtime_has_narration_quality_memory(summary_row):
            warnings.append("narration_quality_memory_not_updated")

    if scenario_name == "npc_bran_refuses_unpaid_room":
        decision = _extract_npc_backbone_decision(summary_row)
        if _safe_str(decision.get("decision")) != "refuse":
            warnings.append("npc_bran_did_not_refuse_unpaid_room")
        if decision.get("accepted") is True:
            warnings.append("npc_bran_unpaid_room_was_accepted")

    if scenario_name == "npc_bran_negotiates_high_trust_room":
        decision = _extract_npc_backbone_decision(summary_row)
        if _safe_str(decision.get("decision")) != "negotiate":
            warnings.append("npc_bran_high_trust_did_not_negotiate")

    if scenario_name == "npc_bran_escalates_when_threatened":
        decision = _extract_npc_backbone_decision(summary_row)
        if _safe_str(decision.get("decision")) != "escalate":
            warnings.append("npc_bran_threat_did_not_escalate")

    if scenario_name == "narration_validator_catches_hit_miss_contradiction":
        warnings_list = _extract_narration_quality_warnings(summary_row)
        if "narration_contradicts_combat_hit" in warnings_list:
            warnings.append("narration_hit_miss_contradiction_present")

    return warnings


def validate_narration_n1_n3_scenario(
    *,
    scenario_name: str,
    scenario_results: List[Dict[str, Any]],
) -> List[str]:
    warnings: List[str] = []

    if scenario_name == "narration_repetition_memory_tracks_recent_output":
        if not any(_runtime_has_narration_quality_memory(row) for row in scenario_results):
            warnings.append("narration_quality_memory_not_updated")

    if scenario_name == "npc_bran_refuses_unpaid_room":
        if not any(
            _safe_str(_extract_npc_backbone_decision(row).get("decision")) == "refuse"
            for row in scenario_results
        ):
            warnings.append("npc_bran_did_not_refuse_unpaid_room")

    if scenario_name == "npc_bran_negotiates_high_trust_room":
        if not any(
            _safe_str(_extract_npc_backbone_decision(row).get("decision")) == "negotiate"
            for row in scenario_results
        ):
            warnings.append("npc_bran_high_trust_did_not_negotiate")

    if scenario_name == "npc_bran_escalates_when_threatened":
        if not any(
            _safe_str(_extract_npc_backbone_decision(row).get("decision")) == "escalate"
            for row in scenario_results
        ):
            warnings.append("npc_bran_threat_did_not_escalate")

    if scenario_name == "narration_validator_catches_hit_miss_contradiction":
        if any(
            "narration_contradicts_combat_hit" in _extract_narration_quality_warnings(row)
            for row in scenario_results
        ):
            warnings.append("narration_hit_miss_contradiction_present")

    return warnings