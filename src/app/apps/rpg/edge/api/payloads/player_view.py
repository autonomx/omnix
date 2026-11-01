"""The campaign as its player may see it: what the play screen reads, and nothing the world keeps private.

The stored campaign holds the world model (each person's secrets, the economy, the pressures), the campaign bible,
creation prompts, NPC memories and the runtime's internals. A route that returns a campaign to the browser returns
this view: the manifest, the public sheet (``state``), and the parts of the simulation and runtime state the play
screen reads (the hero, their needs, the fight, quests, recent events, the journal, the scene).
"""
from __future__ import annotations

from typing import Any, Mapping

SIMULATION_VIEW = frozenset({
    "player_state", "survival", "climate_survival", "combat_state", "quest_state", "present_npc_state",
    "environment", "tick", "turn_index", "location_id", "current_location_id", "current_location_name",
    "recent_events", "timeline", "history", "events", "active_services", "world_items",
})
RUNTIME_VIEW = frozenset({
    "recent_interactions", "player_journal", "campaign_calendar", "current_scene", "last_turn_contract",
    "state_revision", "tick", "dialogue_focus", "turn_history",
})
# The campaign bible holds the world's private canon; the setup payload, how the campaign was made.
_PRIVATE_TOP = frozenset({"simulation_state", "runtime_state", "setup_payload", "campaign_bible_projection"})
_PRIVATE_STATE = frozenset({"campaign_bible"})
# The hero's own record, less what the rules keep about them for later (the rest point is fine to show).
_PLAYER_PRIVATE = frozenset({"progression_log"})


def player_session_view(session: Any) -> Any:
    """``session`` as its player may see it; anything that is not a campaign document is returned as it is."""
    if not isinstance(session, Mapping) or "simulation_state" not in session and "runtime_state" not in session:
        return session
    simulation = session.get("simulation_state") if isinstance(session.get("simulation_state"), Mapping) else {}
    runtime = session.get("runtime_state") if isinstance(session.get("runtime_state"), Mapping) else {}
    view = {key: value for key, value in session.items() if key not in _PRIVATE_TOP}
    if isinstance(view.get("state"), Mapping):
        view["state"] = {key: value for key, value in view["state"].items() if key not in _PRIVATE_STATE}
        view["state"] = _with_pack_actions(view["state"], simulation)
    view["simulation_state"] = {key: value for key, value in simulation.items() if key in SIMULATION_VIEW}
    player = view["simulation_state"].get("player_state")
    if isinstance(player, Mapping):
        view["simulation_state"]["player_state"] = {k: v for k, v in player.items() if k not in _PLAYER_PRIVATE}
    view["runtime_state"] = {key: value for key, value in runtime.items() if key in RUNTIME_VIEW}
    return view


def _with_pack_actions(state: Mapping[str, Any], simulation: Mapping[str, Any]) -> dict[str, Any]:
    """The sheet, each carried thing with what the item rules let the hero do with it and whether it is worn: the
    play screen offers those actions and no others."""
    from app.apps.rpg.rules.interactions.items import is_worn, pack_actions

    player = state.get("player")
    if not isinstance(player, Mapping) or not isinstance(player.get("inventory"), list):
        return dict(state)
    inventory = [
        {**item, "actions": list(pack_actions(simulation, item)), "worn": is_worn(simulation, item)}
        if isinstance(item, Mapping) else item
        for item in player["inventory"]
    ]
    return {**state, "player": {**player, "inventory": inventory}}


def with_player_session_view(payload: dict[str, Any]) -> dict[str, Any]:
    """A route's payload with its campaign, if it has one, as the player may see it."""
    if isinstance(payload, dict) and isinstance(payload.get("session"), Mapping):
        return {**payload, "session": player_session_view(payload["session"])}
    return payload


__all__ = ["RUNTIME_VIEW", "SIMULATION_VIEW", "player_session_view", "with_player_session_view"]
