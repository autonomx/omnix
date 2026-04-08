"""Phase 9.0 — Player inventory helpers.

Connects the player state layer with the inventory subsystem.
"""
from __future__ import annotations

from typing import Any, Dict

from app.rpg.items import build_inventory_summary, ensure_inventory_state


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def ensure_player_inventory(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure *simulation_state* has a well-formed inventory inside player_state."""
    simulation_state = _safe_dict(simulation_state)
    player_state = _safe_dict(simulation_state.get("player_state"))
    player_state = ensure_inventory_state(player_state)
    simulation_state["player_state"] = player_state
    return simulation_state


def build_player_inventory_view(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Return a complete inventory view with state and summary."""
    simulation_state = ensure_player_inventory(simulation_state)
    player_state = _safe_dict(simulation_state.get("player_state"))
    inventory_state = _safe_dict(player_state.get("inventory_state"))
    return {
        "inventory_state": inventory_state,
        "inventory_summary": build_inventory_summary(inventory_state),
    }