"""Phase 10 — Speaker card builders.

Provides deterministic speaker card building for scene and dialogue presentation.
"""
from __future__ import annotations



def build_nearby_npc_cards(simulation_state: dict, scene: dict) -> list:
    """Build dynamic NPC presence cards from scene and simulation state."""
    simulation_state = dict(simulation_state or {})
    scene = dict(scene or {})
    cards = []

    # Gather present NPC IDs from scene
    present_ids = list(scene.get("present_npc_ids", []))
    player_state = dict(simulation_state.get("player_state") or {})
    nearby_ids = list(player_state.get("nearby_npc_ids", []))

    # Merge both lists, dedupe
    all_ids = list(dict.fromkeys(present_ids + nearby_ids))

    # Build NPC index from simulation state
    npcs = simulation_state.get("npcs", [])
    if isinstance(npcs, dict):
        npc_index = npcs
    else:
        npc_index = {}
        for npc in (npcs if isinstance(npcs, list) else []):
            if isinstance(npc, dict):
                npc_id = str(npc.get("npc_id") or npc.get("id") or "")
                if npc_id:
                    npc_index[npc_id] = npc

    # Also check npc_seeds
    for npc in (simulation_state.get("npc_seeds") or []):
        if isinstance(npc, dict):
            npc_id = str(npc.get("npc_id") or npc.get("id") or "")
            if npc_id and npc_id not in npc_index:
                npc_index[npc_id] = npc

    for npc_id in all_ids[:12]:
        npc_id = str(npc_id)
        npc_data = dict(npc_index.get(npc_id, {}))
        card = {
            "npc_id": npc_id,
            "name": str(npc_data.get("name") or npc_id),
            "role": str(npc_data.get("role") or npc_data.get("archetype") or ""),
            "faction": str(npc_data.get("faction") or npc_data.get("faction_id") or ""),
            "portrait": str(npc_data.get("portrait") or ""),
            "attitude_to_player": str(npc_data.get("attitude_to_player") or npc_data.get("disposition") or "neutral"),
            "status_summary": str(npc_data.get("status_summary") or npc_data.get("status") or ""),
            "location_name": str(npc_data.get("location_name") or npc_data.get("location") or ""),
            "is_present": npc_id in present_ids,
            "relationship_tags": list(npc_data.get("relationship_tags") or [])[:5],
        }
        cards.append(card)

    return cards
