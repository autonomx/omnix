"""Phase 15.0 — Migration layer for session payloads.

Provides versioned migration support for old/unversioned saves.
Ensures saves are always normalized to the current schema version
with guaranteed manifest, simulation_state, presentation_state, and memory_state.
"""
from __future__ import annotations

from typing import Any, Dict

_CURRENT_SAVE_VERSION = "1.0"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def migrate_session_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate a session payload from an older schema to the current version.

    - Ensures manifest has an id and schema_version
    - Guarantees simulation_state with presentation_state and memory_state
    - Handles versioned migration for older/unversioned saves
    """
    payload = _safe_dict(payload)
    manifest = _safe_dict(payload.get("manifest"))
    version = int(manifest.get("schema_version") or 1)

    # Ensure manifest has a valid id
    if not manifest.get("id"):
        manifest["id"] = "session:unknown"

    if version < 2:
        # Migrate v1 or unversioned to v2
        simulation_state = _safe_dict(payload.get("simulation_state"))
        presentation_state = _safe_dict(simulation_state.get("presentation_state"))
        memory_state = _safe_dict(simulation_state.get("memory_state"))
        simulation_state["presentation_state"] = presentation_state
        simulation_state["memory_state"] = memory_state
        payload["simulation_state"] = simulation_state
        manifest["schema_version"] = 2
        payload["manifest"] = manifest

    # Always ensure simulation_state has required sub-states
    simulation_state = _safe_dict(payload.get("simulation_state"))
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    memory_state = _safe_dict(simulation_state.get("memory_state"))
    simulation_state["presentation_state"] = presentation_state
    simulation_state["memory_state"] = memory_state
    payload["simulation_state"] = simulation_state
    payload["manifest"] = manifest

    return payload