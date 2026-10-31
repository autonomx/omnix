"""Travel on the pipeline (RQ-2.1): the road from here to a neighbouring place, how long it takes, who is there, and
the quests it advances; or why the hero cannot go. A place further off is one journey, one turn (evolution roadmap
EV-7): the hero goes by the shortest way open now, at most ``MOST_ROADS`` roads, and each place on the way is passed
as any other is arrived at (its people, its quests). The journey stops short where something calls for the hero: a
quest's place reached, or what bars the way on a dangerous road.

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
MOST_ROADS = 4  # the roads one turn's journey takes before the hero stops to look around
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
    if edge is None:
        if not _first_road(graph, simulation, current, target):
            return TravelResolution(
                [counted], [f"No road leads from here to {name}. " + _routes_line(graph, simulation, current)],
                refused=True)
        return _journey(document, graph, counted, current, target)
    return _leg(document, counted, current, target)


def _journey(document: Mapping[str, Any], graph: Any, counted: TurnCounted, current: str,
             target: str) -> TravelResolution:
    """The way to a place further off, one turn: road by road, stopping where a quest's place is reached or the road
    is barred (a dangerous road's creature where the hero would pass), or after ``MOST_ROADS`` roads."""
    from app.apps.rpg.foundation.state.reducer import reduce
    from app.apps.rpg.rules.exploration import room_waits
    from app.apps.rpg.rules.pressures import road_encounter

    goal = _s(_d(_d(_d(_sections.world_model_of(_d(_sections.simulation_state_of(document)))).get("locations"))
                 .get(target)).get("name")) or target
    changes: list[StateChange] = [counted]
    quest_lines: list[str] = []
    seen: list[str] = []  # who is where the journey ends
    minutes, here, travelled, passed = 0, current, dict(document), ""
    told = ""
    for _ in range(MOST_ROADS):
        step = _first_road(graph, _d(_sections.simulation_state_of(travelled)), here, target)
        if not step:
            break
        leg = _leg(travelled, None, here, step)
        changes += leg.changes
        quest_lines += leg.quest_lines
        minutes += leg.minutes
        seen = [line for line in leg.lines if line.startswith("Here: ")]
        travelled, _ = reduce(dict(travelled), leg.changes)
        here = step
        arrived = _d(_sections.simulation_state_of(travelled))
        passed = _s(_d(_d(_d(_sections.world_model_of(arrived)).get("locations")).get(step)).get("name")) or step
        if step == target:
            told = f"You travel to {goal}; the way takes {minutes} minutes."
            break
        quested = any(change.type.startswith("quest_") for change in leg.changes)  # a quest's place reached
        # ... or a site's room that holds its encounter or hazard: rooms are met one by one (EV-10).
        if quested or road_encounter(arrived, turn_key=str(counted.turn_count)) or room_waits(arrived):
            told = f"You set out for {goal} and stop at {passed}, {minutes} minutes on."
            break
    if not told:
        told = f"You set out for {goal}; after {minutes} minutes on the road you are at {passed}."
    return TravelResolution(changes, [told, *seen, *quest_lines], minutes=minutes, destination=here,
                            quest_lines=quest_lines)


def _leg(document: Mapping[str, Any], counted: TurnCounted | None, current: str, target: str) -> TravelResolution:
    """One road, from ``current`` to the neighbouring ``target``: its changes (the turn counted, when ``counted`` is
    given) and what the hero sees there."""
    simulation = _d(_sections.simulation_state_of(document))
    world = _d(_sections.world_model_of(simulation))
    locations = _d(world.get("locations"))
    name = _s(_d(locations.get(target)).get("name")) or target
    minutes = _road_minutes(world, current, target)
    now = clock_minute(document)  # who is there when the hero arrives, the day gone on by the road's time
    present = routines.present_at(simulation, target, now + minutes, since=now)
    first_visit = target not in routines.visited(simulation)  # a first visit to a named place earns experience
    quests, quest_lines = arrival_changes(simulation, target, discovery_xp=DISCOVERY_XP if first_visit else 0)
    changes: list[StateChange] = [
        *([counted] if counted is not None else []),
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
