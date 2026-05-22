from __future__ import annotations

"""N125.2 resource-backed climate source restoration.

Some final autoplay transcript rows preserve climate survival values and a
resource_changes payload, but the compact mirror strips the explicit N123.1
climate source marker.  This helper restores only minimal source metadata when
both pieces of evidence are present. It does not fabricate deltas, actions,
suggestions, warnings, inventory changes, or resource_changes.
"""

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.session.survival_metrics import (
    climate_survival,
    has_climate_tick_source,
    resource_changes,
    row_contract,
    safe_dict,
    safe_list,
)
from app.rpg.session.survival_transcript_sources import has_need_values

RESOURCE_BACKED_CLIMATE_SOURCE = "n1252_projected_resource_change_backed_climate_survival"


def _has_turn_identity(row: Dict[str, Any]) -> bool:
    row = safe_dict(row)
    return row.get("turn_index") is not None or row.get("turn") is not None or row.get("tick") is not None


def _restore_climate_payload(climate: Dict[str, Any]) -> Dict[str, Any]:
    restored = deepcopy(safe_dict(climate))
    restored.setdefault("format_version", "n1231_climate_survival_state_v1")
    restored.setdefault("runtime_enforced", True)
    restored.setdefault("source", RESOURCE_BACKED_CLIMATE_SOURCE)
    return restored


def restore_resource_backed_climate_source(row: Dict[str, Any]) -> Dict[str, Any]:
    source = safe_dict(row)
    projected = deepcopy(source)
    climate = climate_survival(source)
    changes = resource_changes(source)
    if not _has_turn_identity(source):
        return projected
    if not climate or not changes:
        return projected
    if has_climate_tick_source(source):
        return projected
    if not has_need_values(climate):
        return projected

    restored = _restore_climate_payload(climate)
    projected["climate_survival"] = restored

    contract = dict(row_contract(projected) or safe_dict(projected.get("turn_contract")))
    contract["climate_survival"] = restored
    projected["turn_contract"] = contract

    projection = dict(safe_dict(projected.get("survival_evidence_projection")))
    projection.setdefault("format_version", "n1252_survival_transcript_projection_v1")
    projection.setdefault("source", "n1252_resource_backed_source_restoration")
    projection["climate_survival_preserved"] = True
    projection["climate_source_restored"] = True
    projection["restored_climate_source"] = RESOURCE_BACKED_CLIMATE_SOURCE
    projection["resource_backed_climate_source_restored"] = True
    projection["climate_tick_source_present"] = True
    projected["survival_evidence_projection"] = projection
    return projected


def restore_resource_backed_climate_sources(transcript: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [restore_resource_backed_climate_source(row) for row in safe_list(transcript)]
