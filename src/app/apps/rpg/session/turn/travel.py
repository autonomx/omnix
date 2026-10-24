"""Travel on the pipeline (RQ-2.1): the road from here to a neighbouring place, how long it takes, who is there, and
the quests it advances; or why the hero cannot go.

A published world's routes and places are its world model's; a campaign without one (the starter town until
RQ-2.8) takes the older path, since the command grammar has no places to read for it.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state.changes import (
    LocationChanged,
    PresenceChanged,
    StateChange,
    TimeAdvanced,
    TurnCounted,
)
from app.apps.rpg.rules import routines
from app.apps.rpg.rules.quest.arrival import arrival_changes
from app.apps.rpg.session.turn.planning import PlannedAction
from app.apps.rpg.session.turn.world_tick import clock_minute
from app.apps.rpg.world.travel_graph import _edge_is_available, travel_graph_for_state

MINUTES_PER_TICK = 10
DEFAULT_ROAD_MINUTES = 30  # a road the world gives no time for


@dataclass(frozen=True)
class TravelResolution:
    changes: list[StateChange]
    lines: list[str]
    refused: bool = False
    minutes: int = 0
    destination: str = ""
    quest_lines: list[str] = field(default_factory=list)


def _road_minutes(world_model: Mapping[str, Any], origin: str, target: str) -> int:
    for route in _l(world_model.get("routes")):
        route = _d(route)
        if {_s(route.get("from")), _s(route.get("to"))} == {origin, target}:
            match = re.search(r"(\d+)\s*(minute|hour|day)", _s(route.get("travel_time")).lower())
            if match:
                return int(match.group(1)) * {"minute": 1, "hour": 60, "day": 1440}[match.group(2)]
    return DEFAULT_ROAD_MINUTES


def _routes_line(graph: Any, simulation: Mapping[str, Any], current: str) -> str:
    names = [graph.location_name(edge.to_location) for edge in graph.outgoing(current) if _edge_is_available(edge, simulation)]
    return ("Available routes: " + ", ".join(names[:4])) if names else "No routes are currently available."


def resolve_travel(planned: PlannedAction, document: Mapping[str, Any]) -> TravelResolution:
    """The journey's changes and the facts the narrator is told, or a refusal (a counted turn; nothing else changes)."""
    simulation = _d(document.get("simulation_state"))
    world = _d(simulation.get("world_model"))
    locations = _d(world.get("locations"))
    state, manifest = _d(document.get("state")), _d(document.get("manifest"))
    counted = TurnCounted(turn_count=int(state.get("turn_count") or manifest.get("turn_count") or 0) + 1)
    graph = travel_graph_for_state(simulation)
    current = _s(_d(simulation.get("player_state")).get("location_id")) or _s(world.get("start_location_id"))
    target = planned.target_id
    name = _s(_d(locations.get(target)).get("name")) or target
    if target == current:
        return TravelResolution([counted], [f"You are already in {name}. " + _routes_line(graph, simulation, current)],
                                refused=True)
    edge = next((edge for edge in graph.outgoing(current)
                 if edge.to_location == target and _edge_is_available(edge, simulation)), None)
    if edge is None:
        return TravelResolution(
            [counted], [f"No road leads straight from here to {name}. " + _routes_line(graph, simulation, current)],
            refused=True)
    minutes = _road_minutes(world, current, target)
    now = clock_minute(document)  # who is there when the hero arrives, the day gone on by the road's time
    present = routines.present_at(simulation, target, now + minutes, since=now)
    quests, quest_lines = arrival_changes(simulation, target)
    changes: list[StateChange] = [
        counted,
        LocationChanged(location_id=target, location_name=name),
        PresenceChanged(location_id=target, present_npc_ids=tuple(present)),
        TimeAdvanced(ticks=max(1, math.ceil(minutes / MINUTES_PER_TICK)), minutes=minutes),
        *quests,
    ]
    here = routines.described(simulation, present, now + minutes, since=now, hero_at=target)
    # The place's own description reaches the narrator with the scene (runtime_state.current_scene).
    lines = [f"You travel to {name}; the road takes {minutes} minutes."]
    if here:
        lines.append(f"Here: {', '.join(here)}.")
    return TravelResolution(changes, [*lines, *quest_lines], minutes=minutes, destination=target,
                            quest_lines=quest_lines)


__all__ = ["TravelResolution", "resolve_travel"]
