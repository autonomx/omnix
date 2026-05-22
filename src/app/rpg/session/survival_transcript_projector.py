from __future__ import annotations

"""Small N125.2 survival transcript projector.

This replaces the large all-in-one projection helper for the autoplay summary
path. It preserves measurable survival evidence in compact final transcript rows
while remaining idempotent and source-safe.
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
from app.rpg.session.survival_transcript_sources import (
    SURVIVAL_TRANSCRIPT_PROJECTION_FORMAT,
    restore_compacted_climate_source,
)


def _copy_if_present(target: Dict[str, Any], key: str, value: Any) -> bool:
    if isinstance(value, dict) and value:
        target[key] = deepcopy(value)
        return True
    if isinstance(value, list) and value:
        target[key] = deepcopy(value)
        return True
    return False


def persist_survival_evidence_into_transcript_row(row: Dict[str, Any]) -> Dict[str, Any]:
    source = safe_dict(row)
    projected = deepcopy(source)
    contract = dict(row_contract(source))
    had_contract = bool(contract) or isinstance(source.get("turn_contract"), dict)
    projected_contract = dict(safe_dict(projected.get("turn_contract")) or contract)

    climate = climate_survival(source)
    climate, climate_source_restored, restored_source = restore_compacted_climate_source(
        climate=climate,
        contract=contract,
        row=source,
    )
    changes = resource_changes(source)
    effects = effect_result(source)
    action = survival_action(source)
    suggestions = survival_suggestions(source)

    has_climate = False
    if had_contract or climate_source_restored:
        has_climate = _copy_if_present(projected_contract, "climate_survival", climate)
    elif isinstance(climate, dict) and climate:
        has_climate = True

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
