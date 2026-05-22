from __future__ import annotations

"""N125.2 final transcript survival evidence projection.

Autoplay/report rows may be compacted before evaluation summaries are built. This
helper preserves authoritative survival evidence from nested turn-contract/result
payloads into stable final transcript row fields so N125.1 can measure real-run
source coverage instead of only projected survival values.
"""

from copy import deepcopy
from typing import Any, Dict, List, Tuple

from app.rpg.session.survival_metrics import (
    climate_survival,
    effect_result,
    flat_delta,
    has_climate_tick_source,
    resource_changes,
    row_contract,
    safe_dict,
    safe_list,
    survival_action,
    survival_suggestions,
)

SURVIVAL_TRANSCRIPT_PROJECTION_FORMAT = "n1252_survival_transcript_projection_v1"
_COMPACTED_CONTRACT_CLIMATE_SOURCE = "n1252_projected_turn_contract_climate_survival"
_COMPACTED_FINAL_ROW_CLIMATE_SOURCE = "n1252_projected_final_transcript_climate_survival"


def _copy_if_present(target: Dict[str, Any], key: str, value: Any) -> bool:
    if isinstance(value, dict) and value:
        target[key] = deepcopy(value)
        return True
    if isinstance(value, list) and value:
        target[key] = deepcopy(value)
        return True
    return False


def _has_need_values(climate: Dict[str, Any]) -> bool:
    survival = safe_dict(climate.get("survival") or climate.get("values"))
    if climate.get("tick") is None:
        return False
    return all(key in survival for key in ("hunger", "thirst", "fatigue"))


def _is_final_transcript_context(row: Dict[str, Any]) -> bool:
    """Return true for compacted autoplay transcript rows, not display-only values."""

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


def _restore_climate_source(
    *,
    climate: Dict[str, Any],
    contract: Dict[str, Any],
    row: Dict[str, Any],
) -> Tuple[Dict[str, Any], bool, str]:
    """Restore source metadata for compacted authoritative survival rows.

    Real autoplay rows can retain climate survival values while stripping
    non-value metadata such as ``format_version`` and ``source``.  This helper
    restores the minimal N123.1 metadata only for rows that still carry
    authoritative transcript context: nested turn-contract climate rows or final
    transcript rows with player/result/action evidence.  Pure top-level
    value-only runtime display rows are intentionally left source-less.
    """

    climate = safe_dict(climate)
    contract = safe_dict(contract)
    row = safe_dict(row)
    if not climate:
        return {}, False, ""
    if has_climate_tick_source({"climate_survival": climate}):
        return climate, False, ""
    if not _has_need_values(climate):
        return climate, False, ""

    contract_climate = safe_dict(contract.get("climate_survival"))
    if contract_climate and contract_climate == climate:
        restored = deepcopy(climate)
        restored.setdefault("format_version", "n1231_climate_survival_state_v1")
        restored.setdefault("runtime_enforced", True)
        restored.setdefault("source", _COMPACTED_CONTRACT_CLIMATE_SOURCE)
        return restored, True, _COMPACTED_CONTRACT_CLIMATE_SOURCE

    top_level_climate = safe_dict(row.get("climate_survival"))
    if top_level_climate and top_level_climate == climate and _is_final_transcript_context(row):
        restored = deepcopy(climate)
        restored.setdefault("format_version", "n1231_climate_survival_state_v1")
        restored.setdefault("runtime_enforced", True)
        restored.setdefault("source", _COMPACTED_FINAL_ROW_CLIMATE_SOURCE)
        return restored, True, _COMPACTED_FINAL_ROW_CLIMATE_SOURCE

    return climate, False, ""


def persist_survival_evidence_into_transcript_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return a row with stable survival evidence fields preserved.

    The function never fabricates survival values, resource deltas, suggestions,
    or relief actions. It only promotes evidence that already exists somewhere in
    the source row, such as result.turn_contract, authoritative_result, or a
    compacted final transcript row.
    """

    source = safe_dict(row)
    projected = deepcopy(source)
    contract = dict(row_contract(source))
    projected_contract = dict(safe_dict(projected.get("turn_contract")) or contract)

    climate = climate_survival(source)
    climate, climate_source_restored, restored_source = _restore_climate_source(
        climate=climate,
        contract=contract,
        row=source,
    )
    changes = resource_changes(source)
    effects = effect_result(source)
    action = survival_action(source)
    suggestions = survival_suggestions(source)

    has_climate = _copy_if_present(projected_contract, "climate_survival", climate)
    has_changes = _copy_if_present(projected_contract, "resource_changes", changes)
    has_effect = _copy_if_present(projected_contract, "effect_result", effects)
    has_action = _copy_if_present(projected_contract, "survival_action", action)
    has_suggestions = _copy_if_present(projected_contract, "survival_suggested_actions", suggestions)

    if projected_contract:
        projected["turn_contract"] = projected_contract
    _copy_if_present(projected, "climate_survival", climate)
    _copy_if_present(projected, "resource_changes", changes)
    _copy_if_present(projected, "effect_result", effects)
    _copy_if_present(projected, "survival_action", action)
    _copy_if_present(projected, "survival_suggested_actions", suggestions)

    # Add stable convenience deltas for artifact readers. These are derived only
    # from preserved resource_changes and remain zero/absent when no source delta
    # exists.
    if changes:
        projected["hunger_delta"] = flat_delta(projected, "hunger_delta")
        projected["thirst_delta"] = flat_delta(projected, "thirst_delta")
        projected["fatigue_delta"] = flat_delta(projected, "fatigue_delta")

    projected["survival_evidence_projection"] = {
        "format_version": SURVIVAL_TRANSCRIPT_PROJECTION_FORMAT,
        "source": "n1252_final_transcript_row_projection",
        "climate_survival_preserved": has_climate,
        "climate_source_restored": climate_source_restored,
        "restored_climate_source": restored_source,
        "resource_changes_preserved": has_changes,
        "effect_result_preserved": has_effect,
        "survival_action_preserved": has_action,
        "survival_suggestions_preserved": has_suggestions,
        "climate_tick_source_present": has_climate_tick_source(projected),
    }
    return projected


def persist_survival_evidence_into_transcript_rows(transcript: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [persist_survival_evidence_into_transcript_row(row) for row in safe_list(transcript)]
