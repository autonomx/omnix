"""Phase 9.2 — Player party view helpers.

Provides helpers to build party views for the player-facing UI.
"""
from typing import Dict, Any

from app.rpg.party import ensure_party_state, build_party_summary


def _safe_dict(v):
    return v if isinstance(v, dict) else {}


def ensure_player_party(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure simulation_state has normalized party state."""
    simulation_state = _safe_dict(simulation_state)
    player_state = _safe_dict(simulation_state.get("player_state"))
    player_state = ensure_party_state(player_state)
    simulation_state["player_state"] = player_state
    return simulation_state


def build_player_party_view(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Build the full party view for UI display."""
    simulation_state = ensure_player_party(simulation_state)
    player_state = _safe_dict(simulation_state.get("player_state"))
    party_state = _safe_dict(player_state.get("party_state"))
    return {
        "party_state": party_state,
        "party_summary": build_party_summary(player_state),
    }