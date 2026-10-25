"""Persistence normalization for authoritative RPG map session state."""

from __future__ import annotations

from typing import Any

from app.apps.rpg.world.map_world_integration import has_world_map, integrate_canonical_world_map_state


def ensure_session_map_state(session: dict[str, Any]) -> dict[str, Any]:
    """The campaign's map state as its world's maps have it (``map_world_integration.py``); a campaign without a
    world has no maps (the engine has none of its own, roadmap §4.4)."""

    state = session.get("state")
    if isinstance(state, dict) and has_world_map(session):
        return integrate_canonical_world_map_state(session)
    return session
