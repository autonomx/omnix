"""Phase 9.1 — Companion AI for encounters.

Provides simple AI-driven companion actions during tactical encounters.
"""
from typing import Dict, Any

from .party_state import get_active_companions


def run_companion_turns(simulation_state: Dict[str, Any], encounter_state: Dict[str, Any]) -> Dict[str, Any]:
    """Execute companion actions for the current encounter tick.

    Each active companion contributes a simple assist action to the encounter log.
    """
    player_state = simulation_state.get("player_state") or {}
    companions = get_active_companions(player_state)

    if not companions:
        return encounter_state

    encounter_state.setdefault("log", [])

    for comp in sorted(companions, key=lambda c: str(c.get("npc_id")))[:3]:
        encounter_state["log"].append({
            "type": "companion_action",
            "npc_id": comp.get("npc_id"),
            "summary": f"{comp.get('name')} assists in combat.",
        })

    return encounter_state