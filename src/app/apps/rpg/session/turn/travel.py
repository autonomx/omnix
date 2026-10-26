"""Travel on the pipeline (RQ-2.1): the road from here to a neighbouring place, how long it takes, who is there, and
the quests it advances; or why the hero cannot go. A place further off is set out for: the hero takes the first road
of the shortest way there open now, a road a turn, so each place on the way is arrived at as any other (its people,
its quests, what bars the way on a dangerous road).

A published world's routes and places are its world model's; a campaign without one (the starter town until
RQ-2.8) takes the older path, since the command grammar has no places to read for it.
"""
from __future__ import annotations

import math
from collections import deque
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
from app.apps.rpg.rules.player.progression import DISCOVERY_XP
from app.apps.rpg.rules.quest.arrival import arrival_changes
from app.apps.rpg.session.turn.planning import PlannedAction
from app.apps.rpg.session.turn.world_tick import clock_minute
from app.apps.rpg.world.travel_graph import _edge_is_available, travel_graph_for_state
from app.apps.rpg.foundation.state import access as _sections

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


def _first_road(graph: Any, simulation: Mapping[str, Any], current: str, target: str) -> str:
    """The next place on the shortest way from ``current`` to ``target`` by the roads open now; "" when none."""
    previous: dict[str, str] = {current: ""}
    queue = deque([current])
    while queue:
        place = queue.popleft()
        if place == target:
            while previous[place] != current:
                place = previous[place]
            return place
        for edge in graph.outgoing(place):
            if edge.to_location not in previous and _edge_is_available(edge, simulation):
                previous[edge.to_location] = place
                queue.append(edge.to_location)
    return ""


def resolve_travel(planned: PlannedAction, document: Mapping[str, Any]) -> TravelResolution:
    """The journey's changes and the facts the narrator is told, or a refusal (a counted turn; nothing else changes)."""
    simulation = _d(_sections.simulation_state_of(document))
    world = _d(_sections.world_model_of(simulation))
    locations = _d(world.get("locations"))
    state, manifest = _d(document.get("state")), _d(document.get("manifest"))
    counted = TurnCounted(turn_count=int(state.get("turn_count") or manifest.get("turn_count") or 0) + 1)
    graph = travel_graph_for_state(simulation)
    current = _s(_d(_sections.player_state_of(simulation)).get("location_id")) or _s(world.get("start_location_id"))
    target = planned.target_id
    name = _s(_d(locations.get(target)).get("name")) or target
    if target == current:
        return TravelResolution([counted], [f"You are already in {name}. " + _routes_line(graph, simulation, current)],
                                refused=True)
    edge = next((edge for edge in graph.outgoing(current)
                 if edge.to_location == target and _edge_is_available(edge, simulation)), None)
    on_the_way = ""
    if edge is None:
        step = _first_road(graph, simulation, current, target)
        if not step:
            return TravelResolution(
                [counted], [f"No road leads from here to {name}. " + _routes_line(graph, simulation, current)],
                refused=True)
        on_the_way, target = name, step  # set out for it: the first road of the way
        name = _s(_d(locations.get(target)).get("name")) or target
    minutes = _road_minutes(world, current, target)
    now = clock_minute(document)  # who is there when the hero arrives, the day gone on by the road's time
    present = routines.present_at(simulation, target, now + minutes, since=now)
    first_visit = target not in routines.visited(simulation)  # a first visit to a named place earns experience
    quests, quest_lines = arrival_changes(simulation, target, discovery_xp=DISCOVERY_XP if first_visit else 0)
    changes: list[StateChange] = [
        counted,
        LocationChanged(location_id=target, location_name=name),
        PresenceChanged(location_id=target, present_npc_ids=tuple(present)),
        TimeAdvanced(ticks=max(1, math.ceil(minutes / MINUTES_PER_TICK)), minutes=minutes),
        *quests,
    ]
    here = routines.described(simulation, present, now + minutes, since=now, hero_at=target)
    # The place's own description reaches the narrator with the scene (runtime_state.current_scene).
    lines = [f"You set out for {on_the_way}: the way goes by {name}." if on_the_way else "",
             f"You travel to {name}; the road takes {minutes} minutes."]
    lines = [line for line in lines if line]
    if here:
        lines.append(f"Here: {', '.join(here)}.")
    return TravelResolution(changes, [*lines, *quest_lines], minutes=minutes, destination=target,
                            quest_lines=quest_lines)


__all__ = ["TravelResolution", "resolve_travel"]
