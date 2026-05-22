from __future__ import annotations

"""N125.2 final transcript survival evidence projection.

Autoplay/report rows may be compacted before evaluation summaries are built. This
helper preserves authoritative survival evidence from nested turn-contract/result
payloads into stable final transcript row fields so N125.1 can measure real-run
source coverage instead of only projected survival values.
"""

from copy import deepcopy
from typing import Any, Dict, List

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


def _copy_if_present(target: Dict[str, Any], key: str, value: Any) -> bool:
    if isinstance(value, dict) and value:
        target[key] = deepcopy(value)
        return True
    if isinstance(value, list) and value:
        target[key] = deepcopy(value)
        return True
    return False


def persist_survival_evidence_into_transcript_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return a row with stable survival evidence fields preserved.

    The function never fabricates source evidence. It only promotes evidence that
    already exists somewhere in the source row, such as result.turn_contract or
    authoritative_result.turn_contract.
    """

    source = safe_dict(row)
    projected = deepcopy(source)
    contract = dict(row_contract(source))
    projected_contract = dict(safe_dict(projected.get("turn_contract")) or contract)

    climate = climate_survival(source)
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
    # from preserved resource_changes and remain zero when no source delta exists.
    if changes:
        projected["hunger_delta"] = flat_delta(projected, "hunger_delta")
        projected["thirst_delta"] = flat_delta(projected, "thirst_delta")
        projected["fatigue_delta"] = flat_delta(projected, "fatigue_delta")

    projected["survival_evidence_projection"] = {
        "format_version": SURVIVAL_TRANSCRIPT_PROJECTION_FORMAT,
        "source": "n1252_final_transcript_row_projection",
        "climate_survival_preserved": has_climate,
        "resource_changes_preserved": has_changes,
        "effect_result_preserved": has_effect,
        "survival_action_preserved": has_action,
        "survival_suggestions_preserved": has_suggestions,
        "climate_tick_source_present": has_climate_tick_source(projected),
    }
    return projected


def persist_survival_evidence_into_transcript_rows(transcript: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [persist_survival_evidence_into_transcript_row(row) for row in safe_list(transcript)]
