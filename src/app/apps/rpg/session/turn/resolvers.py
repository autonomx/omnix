"""Step 4: each mechanic's resolver says what happens, as changes; it reads the campaign and writes nothing.

Alongside the changes it states the facts the narrator is told (``outcome_lines``): the runtime decides, the
narrator tells.
"""
from __future__ import annotations

from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state.changes import LocationChanged, StateChange, TimeAdvanced, TurnCounted
from app.apps.rpg.rules.location_registry import current_location_id
from app.apps.rpg.session.turn.planning import PlannedAction


def resolve(planned: PlannedAction, document: Mapping[str, Any]) -> list[StateChange]:
    """The changes the action makes: the turn is counted and the time it took passes."""
    state, manifest = _d(document.get("state")), _d(document.get("manifest"))
    count = int(state.get("turn_count") or manifest.get("turn_count") or 0) + 1
    changes: list[StateChange] = [TurnCounted(turn_count=count)]
    simulation = _d(document.get("simulation_state"))
    if not _s(_d(simulation.get("player_state")).get("location_id")):
        # A campaign created without placing the hero (the starter town until RQ-2.8) stands them where its
        # world begins, as the older turn path did on its first turn.
        changes.append(LocationChanged(location_id=current_location_id(dict(simulation))))
    if planned.ticks:
        changes.append(TimeAdvanced(ticks=planned.ticks))
    return changes


def outcome_lines(planned: PlannedAction, document: Mapping[str, Any]) -> list[str]:
    """What the hero perceives, as plain facts for the narration."""
    simulation = _d(document.get("simulation_state"))
    world = _d(simulation.get("world_model"))
    location_id = _s(_d(simulation.get("player_state")).get("location_id") or simulation.get("location_id"))
    location = _d(_d(world.get("locations")).get(location_id))
    name = _s(location.get("name")) or _s(_d(document.get("state")).get("current_location_name")) or "this place"
    people = {**_d(simulation.get("npc_index")), **_d(world.get("npcs"))}
    present = [_s(_d(people.get(npc_id)).get("name")) for npc_id in _l(_d(simulation.get("present_npc_state")).get("present_npc_ids"))]
    present = [person for person in present if person]
    if planned.mechanic == "wait":
        return [f"You wait a while in {name}; time passes.", *([f"Around you: {', '.join(present)}."] if present else [])]
    lines = [f"You look around {name}."]
    if present:
        lines.append(f"Here: {', '.join(present)}.")
    places = _d(world.get("locations"))
    exits = [_s(_d(places.get(_s(place_id))).get("name")) for place_id in _d(location.get("exits")).values()]
    exits = [place for place in dict.fromkeys(exits) if place]
    if exits:
        lines.append(f"Paths lead to {', '.join(exits)}.")
    return lines


__all__ = ["outcome_lines", "resolve"]
