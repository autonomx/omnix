"""Phase 8.2 — Encounter State.

Provides the encounter_state dict structure and ensure_encounter_state helper
that initializes encounter state under simulation_state["player_state"].

Rules:
- participants max 12
- log max 100
- available_actions max 12
- deterministic ordering
"""

from __future__ import annotations

from typing import Any, Dict

# Bounds
_MAX_PARTICIPANTS = 12
_MAX_LOG = 100
_MAX_ACTIONS = 12


def ensure_encounter_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure encounter_state exists under player_state with default values.

    Args:
        simulation_state: The simulation state dict.

    Returns:
        The (possibly modified) simulation_state dict with encounter_state initialized.
    """
    simulation_state = dict(simulation_state or {})
    player_state = simulation_state.setdefault("player_state", {})
    encounter_state = player_state.setdefault("encounter_state", {})
    encounter_state.setdefault("active", False)
    encounter_state.setdefault("encounter_id", "")
    encounter_state.setdefault("scene_id", "")
    encounter_state.setdefault("encounter_type", "")
    encounter_state.setdefault("round", 0)
    encounter_state.setdefault("turn_index", 0)
    encounter_state.setdefault("active_actor_id", "")
    encounter_state.setdefault("participants", [])
    encounter_state.setdefault("log", [])
    encounter_state.setdefault("available_actions", [])
    encounter_state.setdefault("status", "inactive")
    return simulation_state