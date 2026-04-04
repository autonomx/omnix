"""Adapter that converts the creator/game-loop output into the frontend session shape.

The new ``AdventureSetup`` → ``GameLoop.start_new_adventure()`` path returns
``setup`` / ``generated`` / ``canon_summary`` dicts.  The frontend, however,
expects a payload compatible with the legacy ``POST /api/rpg/games`` response
(``opening``, ``world``, ``player``, ``npcs``, ``memory``, ``worldEvents``).

This thin conversion layer bridges the gap so the UI has a stable contract
regardless of which creation path produced the data.
"""

from __future__ import annotations

import uuid
from typing import Any


def adapt_start_result(result: dict[str, Any]) -> dict[str, Any]:
    """Convert ``GameLoop.start_new_adventure()`` output to frontend shape.

    Parameters
    ----------
    result:
        The dict returned by ``GameLoop.start_new_adventure()``.
        Expected keys: ``ok``, ``setup``, ``generated``, ``canon_summary``.

    Returns
    -------
    dict
        Frontend-friendly payload with ``session_id``, ``opening``, ``world``,
        ``player``, ``npcs``, ``memory``, ``worldEvents``, plus the raw
        ``setup`` / ``generated`` / ``canon_summary`` for advanced consumers.
    """
    setup = result.get("setup", {})
    generated = result.get("generated", {})
    canon_summary = result.get("canon_summary", {})

    world_frame = generated.get("world_frame", {})
    opening_situation = generated.get("opening_situation", {})
    seed_npcs = generated.get("seed_npcs", [])
    seed_locations = generated.get("seed_locations", [])
    seed_factions = generated.get("seed_factions", [])

    # Build the opening narration from the generated opening situation.
    opening_parts: list[str] = []
    if opening_situation.get("summary"):
        opening_parts.append(opening_situation["summary"])
    if opening_situation.get("location"):
        opening_parts.append(f"You find yourself in {opening_situation['location']}.")
    if opening_situation.get("present_actors"):
        actors = ", ".join(opening_situation["present_actors"])
        opening_parts.append(f"Present: {actors}.")
    opening = " ".join(opening_parts) if opening_parts else "Your adventure begins\u2026"

    # World payload
    world = {
        "name": world_frame.get("title", ""),
        "genre": world_frame.get("genre", ""),
        "description": world_frame.get("setting", ""),
    }

    # Player stub — the creator pipeline does not define a player yet, so we
    # return a minimal default.  Downstream systems can enrich this.
    player = {
        "id": "player_1",
        "name": setup.get("metadata", {}).get("player_name", "Player"),
        "hp": 100,
        "profile": {},
    }

    # NPC list → lightweight cards for the frontend
    npcs = [
        {
            "id": npc.get("npc_id", ""),
            "name": npc.get("name", "Unknown"),
            "role": npc.get("role", ""),
            "description": npc.get("description", ""),
            "faction_id": npc.get("faction_id"),
            "location_id": npc.get("location_id"),
        }
        for npc in seed_npcs
    ]

    # Memory / world events — pull from canon summary if available
    memory: list[str] = []
    world_events: list[str] = []
    if canon_summary.get("facts"):
        for fact in canon_summary["facts"]:
            if isinstance(fact, dict):
                memory.append(f"{fact.get('subject', '')}: {fact.get('value', '')}")
            elif isinstance(fact, str):
                memory.append(fact)
    if opening_situation.get("active_tensions"):
        world_events.extend(opening_situation["active_tensions"])

    session_id = setup.get("setup_id") or str(uuid.uuid4())

    return {
        "success": True,
        "session_id": session_id,
        "opening": opening,
        "world": world,
        "player": player,
        "npcs": npcs,
        "memory": memory,
        "worldEvents": world_events,
        # Raw structured data for advanced / debug consumers
        "setup": setup,
        "generated": generated,
        "canon_summary": canon_summary,
    }
