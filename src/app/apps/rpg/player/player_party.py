"""Phase 9.2/9.3/10 — Player party view helpers.

Provides helpers to build party views for the player-facing UI,
including Phase 9.3 companion narrative presence summaries
and Phase 10 presentation speaker cards.
"""
from typing import Any, Dict, List

from app.rpg.party import (
    build_companion_presence_summary,
    build_party_summary,
    ensure_party_state,
)
from app.rpg.presentation import build_party_speaker_cards


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
    return list(v) if isinstance(v, list) else []


def ensure_player_party(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure simulation_state has normalized party state."""
    simulation_state = _safe_dict(simulation_state)
    player_state = _safe_dict(simulation_state.get("player_state"))
    player_state = ensure_party_state(player_state)
    simulation_state["player_state"] = player_state
    return simulation_state


def build_player_party_view(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Build the full party view for UI display, including narrative presence and speaker cards."""
    simulation_state = ensure_player_party(simulation_state)
    player_state = _safe_dict(simulation_state.get("player_state"))
    party_state = _safe_dict(player_state.get("party_state"))
    companions = [
        comp
        for comp in _safe_list(party_state.get("companions") or [])
        if isinstance(comp, dict) and str(comp.get("status") or "active") == "active"
    ]
    return {
        "party_state": party_state,
        "party_summary": build_party_summary(player_state),
        "presence_summary": build_companion_presence_summary(player_state),
        "speaker_cards": build_party_speaker_cards(simulation_state, companions),
    }
