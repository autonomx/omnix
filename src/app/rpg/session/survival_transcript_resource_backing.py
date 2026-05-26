from __future__ import annotations

"""N125.2 resource-backed climate source restoration.

Some final autoplay transcript rows preserve climate survival values and a
resource_changes payload, but the compact mirror strips the explicit N123.1
climate source marker.  This helper restores only minimal source metadata when
both pieces of evidence are present. It does not fabricate deltas, actions,
suggestions, warnings, inventory changes, or resource_changes.

Longer autoplay runs can carry large nested presentation/report payloads on each
transcript row.  Restoration must therefore avoid deepcopying whole rows.  It
uses a shallow top-level row copy plus selective small payload copies for the
fields it mutates.
"""

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.session.survival_metrics import (
    climate_survival,
    resource_changes,
    row_contract,
    safe_dict,
    safe_list,
)
from app.rpg.session.survival_transcript_sources import has_need_values

RESOURCE_BACKED_CLIMATE_SOURCE = "n1252_projected_resource_change_backed_climate_survival"
_EXPLICIT_CLIMATE_SOURCE_VALUES = {
    "deterministic_authoritative_turn_tick",
    "n1252_projected_resource_change_backed_climate_survival",
    "n1252_projected_final_transcript_climate_survival",
    "n1252_projected_turn_contract_climate_survival",
}


def _has_turn_identity(row: Dict[str, Any]) -> bool:
    row = safe_dict(row)
    return row.get("turn_index") is not None or row.get("turn") is not None or row.get("tick") is not None


def _small_payload_copy(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Copy a small targeted payload without recursively cloning the whole row."""

    return deepcopy(safe_dict(payload))


def _has_explicit_climate_source(climate: Dict[str, Any], changes: Dict[str, Any]) -> bool:
    """Return true only when explicit source metadata already exists.

    survival_metrics.has_climate_tick_source intentionally treats climate values
    plus resource_changes as source-backed evidence.  This restoration helper is
    the step that adds the missing source metadata for exactly that case, so it
    must not use the broader inferred-source predicate as a short circuit.
    """

    climate = safe_dict(climate)
    changes = safe_dict(changes)
    source = str(climate.get("source") or "")
    format_version = str(climate.get("format_version") or "")
    if source in _EXPLICIT_CLIMATE_SOURCE_VALUES:
        return True
    if format_version == "n1231_climate_survival_state_v1":
        return True
    if climate.get("runtime_enforced") is True and format_version.startswith("n1231_"):
        return True
    if changes.get("source") == "n1231_climate_survival_tick":
        return True
    climate_changes = safe_dict(changes.get("climate_survival"))
    if climate_changes.get("source") == "n1231_climate_survival_tick":
        return True
    return False


def _restore_climate_payload(climate: Dict[str, Any]) -> Dict[str, Any]:
    restored = _small_payload_copy(climate)
    restored.setdefault("format_version", "n1231_climate_survival_state_v1")
    restored.setdefault("runtime_enforced", True)
    restored.setdefault("source", RESOURCE_BACKED_CLIMATE_SOURCE)
    return restored


def restore_resource_backed_climate_source(row: Dict[str, Any]) -> Dict[str, Any]:
    source = safe_dict(row)
    climate = climate_survival(source)
    changes = resource_changes(source)

    # Fast path: unchanged rows should be returned as-is.  This avoids allocating
    # a second copy of large transcript rows when no restoration is needed.
    if not _has_turn_identity(source):
        return source
    if not climate or not changes:
        return source
    if _has_explicit_climate_source(climate, changes):
        return source
    if not has_need_values(climate):
        return source

    # Only the top-level row, turn_contract, climate_survival, and projection
    # fields are mutated.  Everything else can safely remain shared with the
    # source row because this helper is a projection pass, not a row sanitizer.
    projected = dict(source)
    restored = _restore_climate_payload(climate)
    projected["climate_survival"] = restored

    contract_source = row_contract(projected) or safe_dict(projected.get("turn_contract"))
    contract = _small_payload_copy(contract_source)
    contract["climate_survival"] = restored
    projected["turn_contract"] = contract

    projection = _small_payload_copy(safe_dict(projected.get("survival_evidence_projection")))
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
