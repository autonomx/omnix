from __future__ import annotations

"""Small N125.2 helpers for deciding whether compacted survival rows are source-backed.

These helpers intentionally do not fabricate survival values, deltas, actions,
or suggestions. They only restore minimal source metadata when a compacted row
still carries enough transcript context to be treated as an authoritative final
transcript row.
"""

from copy import deepcopy
from typing import Any, Dict, Tuple

from app.rpg.session.survival_metrics import has_climate_tick_source, safe_dict

SURVIVAL_TRANSCRIPT_PROJECTION_FORMAT = "n1252_survival_transcript_projection_v1"
COMPACTED_CONTRACT_CLIMATE_SOURCE = "n1252_projected_turn_contract_climate_survival"
COMPACTED_FINAL_ROW_CLIMATE_SOURCE = "n1252_projected_final_transcript_climate_survival"


def has_need_values(climate: Dict[str, Any]) -> bool:
    climate = safe_dict(climate)
    survival = safe_dict(climate.get("survival") or climate.get("values"))
    if climate.get("tick") is None:
        return False
    return all(key in survival for key in ("hunger", "thirst", "fatigue"))


def is_final_transcript_context(row: Dict[str, Any]) -> bool:
    row = safe_dict(row)
    if row.get("turn_index") is None and row.get("turn") is None:
        return False
    evidence_keys = (
        "player",
        "player_action",
        "action",
        "canonical_turn_action",
        "narration",
        "result",
        "authoritative_result",
        "raw_result",
        "resolved_action",
        "resolved_result",
        "resource_changes",
        "effect_result",
    )
    return any(key in row for key in evidence_keys)


def projection_was_value_only(row: Dict[str, Any]) -> bool:
    projection = safe_dict(safe_dict(row).get("survival_evidence_projection"))
    return (
        projection.get("format_version") == SURVIVAL_TRANSCRIPT_PROJECTION_FORMAT
        and projection.get("climate_survival_preserved") is True
        and projection.get("climate_source_restored") is False
        and not projection.get("restored_climate_source")
        and projection.get("resource_changes_preserved") is False
        and projection.get("effect_result_preserved") is False
        and projection.get("survival_action_preserved") is False
        and projection.get("survival_suggestions_preserved") is False
    )


def restore_compacted_climate_source(
    *,
    climate: Dict[str, Any],
    contract: Dict[str, Any],
    row: Dict[str, Any],
) -> Tuple[Dict[str, Any], bool, str]:
    climate = safe_dict(climate)
    contract = safe_dict(contract)
    row = safe_dict(row)
    if not climate:
        return {}, False, ""
    if has_climate_tick_source({"climate_survival": climate}):
        return climate, False, ""
    if not has_need_values(climate):
        return climate, False, ""

    previously_value_only = projection_was_value_only(row)
    contract_climate = safe_dict(contract.get("climate_survival"))
    if contract_climate and contract_climate == climate and not previously_value_only:
        restored = deepcopy(climate)
        restored.setdefault("format_version", "n1231_climate_survival_state_v1")
        restored.setdefault("runtime_enforced", True)
        restored.setdefault("source", COMPACTED_CONTRACT_CLIMATE_SOURCE)
        return restored, True, COMPACTED_CONTRACT_CLIMATE_SOURCE

    top_level_climate = safe_dict(row.get("climate_survival"))
    if top_level_climate and top_level_climate == climate and is_final_transcript_context(row):
        restored = deepcopy(climate)
        restored.setdefault("format_version", "n1231_climate_survival_state_v1")
        restored.setdefault("runtime_enforced", True)
        restored.setdefault("source", COMPACTED_FINAL_ROW_CLIMATE_SOURCE)
        return restored, True, COMPACTED_FINAL_ROW_CLIMATE_SOURCE

    return climate, False, ""
