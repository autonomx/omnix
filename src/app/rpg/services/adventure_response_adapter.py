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

# ---------------------------------------------------------------------------
# Response version constants — bump when the response contract changes
# ---------------------------------------------------------------------------

ADVENTURE_START_RESPONSE_VERSION = 1


# ---------------------------------------------------------------------------
# Safety helpers — guard against malformed/partial internal output
# ---------------------------------------------------------------------------


def _safe_list(value: Any) -> list[Any]:
    """Return *value* if it is already a list, otherwise ``[]``."""
    if isinstance(value, list):
        return value
    return []


def _safe_dict(value: Any) -> dict[str, Any]:
    """Return *value* if it is already a dict, otherwise ``{}``."""
    if isinstance(value, dict):
        return value
    return {}


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
        Frontend-friendly payload with ``response_version``, ``success``,
        ``session_id``, ``opening``, ``world``, ``player``, ``npcs``,
        ``locations``, ``factions``, ``memory``, ``worldEvents``, and
        ``creator`` metadata.
    """
    generated = _safe_dict(result.get("generated"))
    setup = _safe_dict(result.get("setup"))
    canon_summary = _safe_dict(result.get("canon_summary"))

    seed_npcs = _safe_list(generated.get("seed_npcs"))
    seed_locations = _safe_list(generated.get("seed_locations"))
    seed_factions = _safe_list(generated.get("seed_factions"))

    # Build the opening narration from the generated opening situation.
    opening_situation = _safe_dict(generated.get("opening_situation"))
    opening_parts: list[str] = []
    if opening_situation.get("summary"):
        opening_parts.append(opening_situation["summary"])
    if opening_situation.get("location"):
        opening_parts.append(f"You find yourself in {opening_situation['location']}.")
    if opening_situation.get("present_actors"):
        actors = ", ".join(opening_situation["present_actors"])
        opening_parts.append(f"Present: {actors}.")
    opening = " ".join(opening_parts) if opening_parts else "Your adventure begins…"

    # World payload
    world_frame = _safe_dict(generated.get("world_frame"))
    world = {
        "title": setup.get("title") or world_frame.get("title") or "",
        "genre": setup.get("genre") or "",
        "setting": setup.get("setting") or "",
        "premise": setup.get("premise") or "",
        "summary": canon_summary.get("summary") or "",
    }

    # Player stub — the creator pipeline does not define a player yet, so we
    # return a minimal default.  Downstream systems can enrich this.
    setup_metadata = _safe_dict(setup.get("metadata"))
    player = {
        "name": setup_metadata.get("player_name", "Player"),
    }

    #NPC list → lightweight cards for the frontend
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
        if isinstance(npc, dict)
    ]

    # Memory / world events — pull from canon summary if available
    memory = _safe_list(canon_summary.get("facts"))
    world_events = _safe_list(generated.get("initial_threads"))

    session_id = setup.get("setup_id") or str(uuid.uuid4())

    response = {
        "response_version": ADVENTURE_START_RESPONSE_VERSION,
        "success": True,
        "session_id": session_id,
        "opening": opening,
        "world": world,
        "player": player,
        "npcs": npcs,
        "locations": seed_locations,
        "factions": seed_factions,
        "memory": memory,
        "worldEvents": world_events,
        "creator": {
            "setup_id": setup.get("setup_id"),
            "template_name": setup_metadata.get("template_name"),
        },
    }
    return response