"""Migration v5 -> v6: Add companion intelligence fields.

This migration adds HP, max_hp, loyalty, morale, status, role, and equipment
fields to existing companion records.

Fix #4: Migration now uses _normalize_companion to ensure full normalization
of companion records, including proper equipment structure, edge cases for
missing fields, and malformed companions from earlier saves.
"""
from typing import Dict, Any

from app.rpg.party.party_state import _normalize_companion


def _safe_dict(v):
    return v if isinstance(v, dict) else {}


def migrate_v5_to_v6(package: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate a v5 save package to v6 schema.

    Uses _normalize_companion for full record normalization.
    """
    package = dict(package or {})
    state = _safe_dict(package.get("state"))
    simulation_state = _safe_dict(state.get("simulation_state"))
    player_state = _safe_dict(simulation_state.get("player_state"))
    party_state = _safe_dict(player_state.get("party_state"))

    # Fix #4: Use _normalize_companion for complete normalization
    companions = []
    seen_ids = set()
    for comp in party_state.get("companions") or []:
        if isinstance(comp, dict) and comp.get("npc_id"):
            npc_id = comp.get("npc_id")
            if npc_id not in seen_ids:
                seen_ids.add(npc_id)
                companions.append(_normalize_companion(comp))

    # Deduplicated, normalized companion list
    companions = sorted(companions, key=lambda c: str(c.get("npc_id")))
    companions = companions[:6]  # Cap at 6 companions

    party_state["companions"] = companions
    party_state.setdefault("max_size", 3)
    player_state["party_state"] = party_state
    simulation_state["player_state"] = player_state
    state["simulation_state"] = simulation_state
    package["state"] = state
    package["schema_version"] = 6
    return package