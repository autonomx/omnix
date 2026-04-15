"""Frontend payload adapter for canonical RPG sessions.

The creator/start flow now persists a canonical session immediately.
The frontend still expects a stable bootstrap payload:
``session_id``, ``opening``, ``world``, ``player``, ``npcs``, ``memory``,
``worldEvents``.
"""

from __future__ import annotations

from typing import Any

from app.rpg.items.inventory_state import normalize_inventory_state

# ---------------------------------------------------------------------------
# Response version constants — bump when the contract changes
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


def adapt_session_to_frontend(session: dict[str, Any]) -> dict[str, Any]:
    """Convert canonical persisted session to frontend shape.

    Parameters
    ----------
    session:
        The dict returned by the canonical session store.
        Expected keys: ``manifest``, ``runtime_state``, ``simulation_state``.

    Returns
    -------
    dict
        Frontend-friendly payload derived from canonical persisted session state.
    """
    session = _safe_dict(session)
    manifest = _safe_dict(session.get("manifest"))
    runtime_state = _safe_dict(session.get("runtime_state"))
    simulation_state = _safe_dict(session.get("simulation_state"))
    player_state = _safe_dict(simulation_state.get("player_state"))
    current_scene = _safe_dict(runtime_state.get("current_scene"))
    inventory_state = normalize_inventory_state(_safe_dict(player_state.get("inventory_state")))

    # Build nearby NPC cards
    from app.rpg.presentation.speaker_cards import build_nearby_npc_cards
    nearby_npc_cards = build_nearby_npc_cards(simulation_state, current_scene)

    # Memory summary
    from app.rpg.presentation.memory_inspector import build_memory_ui_summary
    memory_summary = build_memory_ui_summary(simulation_state)

    response = {
        "response_version": ADVENTURE_START_RESPONSE_VERSION,
        "success": True,
        "session_id": manifest.get("session_id"),
        "title": manifest.get("title"),
        "opening": runtime_state.get("opening") or "",
        "narration": runtime_state.get("opening") or "",
        "world": _safe_dict(runtime_state.get("world")),
        "player": {
            "stats": _safe_dict(player_state.get("stats")),
            "skills": _safe_dict(player_state.get("skills")),
            "level": int(player_state.get("level", 1) or 1),
            "xp": int(player_state.get("xp", 0) or 0),
            "xp_to_next": int(player_state.get("xp_to_next", 100) or 100),
            "inventory_state": inventory_state,
            "equipment": _safe_dict(inventory_state.get("equipment")),
            "currency": _safe_dict(inventory_state.get("currency")),
            "inventory_items": _safe_list(inventory_state.get("items")),
            "nearby_npc_ids": _safe_list(player_state.get("nearby_npc_ids")),
            "available_checks": _safe_list(player_state.get("available_checks")),
        },
        "nearby_npcs": nearby_npc_cards,
        "known_npcs": _safe_list(runtime_state.get("npcs")),
        "scene": {
            "scene_id": str(current_scene.get("scene_id", "")),
            "items": _safe_list(current_scene.get("items")),
            "available_checks": _safe_list(current_scene.get("available_checks")),
            "present_npc_ids": _safe_list(current_scene.get("present_npc_ids")),
        },
        "memory_summary": memory_summary,
        "combat_result": {},
        "xp_result": {},
        "skill_xp_result": {},
        "level_up": [],
        "skill_level_ups": [],
        "presentation": {},
        # Legacy compatibility fields
        "npcs": _safe_list(runtime_state.get("npcs")),
        "memory": _safe_list(_safe_dict(simulation_state.get("memory_state")).get("short_term")),
        "worldEvents": _safe_list(simulation_state.get("events"))[-8:],
        "world_events": _safe_list(simulation_state.get("events"))[-8:],
        "voice_assignments": _safe_dict(runtime_state.get("voice_assignments")),
        "creator": {"setup_id": manifest.get("id")},
    }

    return response