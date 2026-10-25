"""Phase 18.3A — World item state: ground loot and scene objects."""
from __future__ import annotations

from typing import Any, Dict


def ensure_world_item_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure simulation_state has a well-formed world_items subtree."""
    simulation_state = dict(simulation_state or {})
    wi = simulation_state.setdefault("world_items", {})
    if not isinstance(wi, dict):
        simulation_state["world_items"] = {"by_location": {}}
    wi = simulation_state["world_items"]
    wi.setdefault("by_location", {})
    return simulation_state
