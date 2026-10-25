# N82-N84 — Travel Graph + Location Progression v1

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
from app.apps.rpg.foundation.state import access as _sections


@dataclass(frozen=True)
class TravelEdge:
    from_location: str
    to_location: str
    label: str = ""
    direction: str = ""
    aliases: Tuple[str, ...] = ()
    required_flags: Tuple[str, ...] = ()
    blocked_by_flags: Tuple[str, ...] = ()
    travel_time_ticks: int = 1
    difficulty: str = "normal"


@dataclass
class TravelGraph:
    locations: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    edges: List[TravelEdge] = field(default_factory=list)

    def add_location(self, location_id: str, **metadata: Any) -> None:
        if not location_id:
            return
        existing = self.locations.setdefault(location_id, {})
        existing.update(metadata)

    def add_edge(
        self,
        from_location: str,
        to_location: str,
        *,
        label: str = "",
        direction: str = "",
        aliases: Iterable[str] = (),
        required_flags: Iterable[str] = (),
        blocked_by_flags: Iterable[str] = (),
        travel_time_ticks: int = 1,
        difficulty: str = "normal",
        bidirectional: bool = True,
    ) -> None:
        edge = TravelEdge(
            from_location=from_location,
            to_location=to_location,
            label=label or to_location,
            direction=direction,
            aliases=tuple(aliases),
            required_flags=tuple(required_flags),
            blocked_by_flags=tuple(blocked_by_flags),
            travel_time_ticks=max(1, int(travel_time_ticks or 1)),
            difficulty=difficulty or "normal",
        )
        self.edges.append(edge)

        if bidirectional:
            reverse_direction = _reverse_direction(direction)
            self.edges.append(
                TravelEdge(
                    from_location=to_location,
                    to_location=from_location,
                    label=self.locations.get(from_location, {}).get("name") or from_location,
                    direction=reverse_direction,
                    aliases=tuple(aliases),
                    required_flags=tuple(required_flags),
                    blocked_by_flags=tuple(blocked_by_flags),
                    travel_time_ticks=max(1, int(travel_time_ticks or 1)),
                    difficulty=difficulty or "normal",
                )
            )

    def outgoing(self, location_id: str) -> List[TravelEdge]:
        return [edge for edge in self.edges if edge.from_location == location_id]

    def location_name(self, location_id: str) -> str:
        meta = self.locations.get(location_id) or {}
        return str(meta.get("name") or location_id)


def _reverse_direction(direction: str) -> str:
    value = (direction or "").strip().lower()
    return {
        "north": "south",
        "south": "north",
        "east": "west",
        "west": "east",
        "up": "down",
        "down": "up",
        "inside": "outside",
        "outside": "inside",
    }.get(value, "")


def _normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9:_\-\s]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Words of route labels and place names that say nothing about where a route goes ("travel to X").
_ROUTE_FILLER_WORDS = frozenset({"a", "an", "and", "at", "go", "in", "of", "on", "the", "to", "travel"})


def _named_location(normalized: str, graph: "TravelGraph") -> str:
    """The place the input names in full (the longest such name), or ""."""
    found, length = "", 0
    for location_id in graph.locations:
        name = _normalize_text(graph.location_name(location_id))
        if len(name) > length and re.search(rf"(?<![\w:-]){re.escape(name)}(?![\w:-])", normalized):
            found, length = location_id, len(name)
    return found


def _state_flags(state: Mapping[str, Any]) -> set[str]:
    flags: set[str] = set()
    raw_flags = state.get("flags")
    if isinstance(raw_flags, Mapping):
        flags.update(str(k) for k, v in raw_flags.items() if v)
    elif isinstance(raw_flags, list):
        flags.update(str(v) for v in raw_flags)

    world_flags = state.get("world_flags")
    if isinstance(world_flags, Mapping):
        flags.update(str(k) for k, v in world_flags.items() if v)
    elif isinstance(world_flags, list):
        flags.update(str(v) for v in world_flags)

    return flags


def _edge_is_available(edge: TravelEdge, state: Mapping[str, Any]) -> bool:
    flags = _state_flags(state)
    if any(flag not in flags for flag in edge.required_flags):
        return False
    if any(flag in flags for flag in edge.blocked_by_flags):
        return False
    return True


def _world_model(state: Mapping[str, Any]) -> Mapping[str, Any]:
    world_model = _sections.world_model_of(state) if isinstance(state, Mapping) else None
    return world_model if isinstance(world_model, Mapping) and world_model.get("locations") else {}


def _travel_ticks(travel_time: str) -> int:
    """Turn ticks for a route's travel time ("20 minutes", "4 hours"): one tick per started hour."""
    match = re.search(r"(\d+)\s*(minute|hour|day)", travel_time.lower())
    if not match:
        return 1
    minutes = int(match.group(1)) * {"minute": 1, "hour": 60, "day": 1440}[match.group(2)]
    return max(1, -(-minutes // 60))


def travel_graph_for_state(state: Mapping[str, Any]) -> TravelGraph:
    """The campaign's routes: its world model's (every campaign plays from a world; the engine has none of its own)."""
    world_model = _world_model(state)
    graph = TravelGraph()
    if not world_model:
        return graph
    for location_id, location in dict(world_model.get("locations") or {}).items():
        if isinstance(location, Mapping):
            graph.add_location(
                location_id,
                name=str(location.get("name") or location_id),
                aliases=list(location.get("aliases") or []),
                kind="published_location",
            )
    linked: set[tuple[str, str]] = set()
    for route in world_model.get("routes") or ():
        if not isinstance(route, Mapping):
            continue
        origin, target = str(route.get("from") or ""), str(route.get("to") or "")
        if origin not in graph.locations or target not in graph.locations:
            continue
        # A route runs both ways; each way is named by where it leads (a reversed edge would keep the
        # other end's name as its alias, so "go to Starfall Village" in the village led back out of it).
        for start, end in ((origin, target), (target, origin)):
            if (start, end) in linked:
                continue
            linked.add((start, end))
            graph.add_edge(
                start,
                end,
                label=f"travel to {graph.location_name(end)}",
                aliases=[graph.location_name(end).lower()],
                travel_time_ticks=_travel_ticks(str(route.get("travel_time") or "")),
                bidirectional=False,
            )
    return graph


def get_current_location(state: Mapping[str, Any]) -> str:
    player_state = _sections.player_state_of(state) if isinstance(_sections.player_state_of(state), Mapping) else {}
    return str(
        state.get("current_location")
        or state.get("current_location_id")
        or (_world_model(state) and player_state.get("location_id"))
        or state.get("location")
        or _world_model(state).get("start_location_id")
        or ""
    )


def list_available_routes(
    *,
    state: Mapping[str, Any],
    graph: Optional[TravelGraph] = None,
) -> List[Dict[str, Any]]:
    graph = graph or travel_graph_for_state(state)
    current = get_current_location(state)
    routes: List[Dict[str, Any]] = []
    for edge in graph.outgoing(current):
        if not _edge_is_available(edge, state):
            continue
        routes.append(
            {
                "from_location": edge.from_location,
                "to_location": edge.to_location,
                "to_name": graph.location_name(edge.to_location),
                "label": edge.label,
                "direction": edge.direction,
                "aliases": list(edge.aliases),
                "travel_time_ticks": edge.travel_time_ticks,
                "difficulty": edge.difficulty,
            }
        )
    return routes


def resolve_travel_destination(
    *,
    player_input: str,
    state: Mapping[str, Any],
    graph: Optional[TravelGraph] = None,
) -> Dict[str, Any]:
    graph = graph or travel_graph_for_state(state)
    current = get_current_location(state)
    normalized = _normalize_text(player_input)

    travel_intent = bool(
        re.search(
            r"\b(go|travel|walk|head|leave|enter|follow|move|continue|take|return|north|south|east|west|outside|inside)\b",
            normalized,
        )
    )

    if not travel_intent:
        return {
            "ok": False,
            "reason": "not_travel_intent",
            "current_location": current,
            "available_routes": list_available_routes(state=state, graph=graph),
        }

    candidates: List[Tuple[int, TravelEdge]] = []
    words = set(normalized.split())

    for edge in graph.outgoing(current):
        if not _edge_is_available(edge, state):
            continue

        score = 0
        to_meta = graph.locations.get(edge.to_location) or {}
        names = [
            edge.to_location,
            graph.location_name(edge.to_location),
            edge.direction,
            edge.label,
            *(edge.aliases or ()),
            *list(to_meta.get("aliases") or []),
        ]

        for raw_name in names:
            name = _normalize_text(raw_name)
            if not name:
                continue
            if name == normalized:
                score += 100
            elif name in normalized:
                score += 50
            elif any(part in words for part in name.split() if part not in _ROUTE_FILLER_WORDS):
                score += 8

        if edge.direction and re.search(rf"\b{re.escape(edge.direction.lower())}\b", normalized):
            score += 35

        if score > 0:
            candidates.append((score, edge))

    named = _named_location(normalized, graph)
    if not candidates and not named:
        return {
            "ok": False,
            "reason": "unknown_or_unreachable_destination",
            "current_location": current,
            "current_location_name": graph.location_name(current),
            "available_routes": list_available_routes(state=state, graph=graph),
        }

    candidates.sort(key=lambda item: item[0], reverse=True)
    score, edge = candidates[0] if candidates else (0, None)
    if edge is None or (score < 50 and named and named != edge.to_location):
        # The player named a place in full that no route from here reaches (or the place they are in); a
        # route sharing one of its words ("Starfall Grove" for "Starfall Village") is not where they meant.
        return {
            "ok": False,
            "reason": "already_here" if named == current else "destination_not_adjacent",
            "current_location": current,
            "current_location_name": graph.location_name(current),
            "named_location": named,
            "named_location_name": graph.location_name(named),
            "available_routes": list_available_routes(state=state, graph=graph),
        }

    return {
        "ok": True,
        "reason": "route_resolved",
        "score": score,
        "from_location": edge.from_location,
        "from_location_name": graph.location_name(edge.from_location),
        "to_location": edge.to_location,
        "to_location_name": graph.location_name(edge.to_location),
        "label": edge.label,
        "direction": edge.direction,
        "travel_time_ticks": edge.travel_time_ticks,
        "difficulty": edge.difficulty,
        "available_routes": list_available_routes(state=state, graph=graph),
    }


def apply_travel_result_to_state(
    *,
    state: Mapping[str, Any],
    travel_result: Mapping[str, Any],
) -> Dict[str, Any]:
    next_state = dict(state or {})
    if not travel_result.get("ok"):
        return next_state

    to_location = str(travel_result.get("to_location") or "")
    if not to_location:
        return next_state

    previous = get_current_location(next_state)
    next_state["previous_location"] = previous
    next_state["current_location"] = to_location
    next_state["current_location_id"] = to_location
    next_state["current_location_name"] = str(travel_result.get("to_location_name") or to_location)

    if _world_model(next_state):
        # The location registry reads the player's place; keep it with the route the party took.
        player_state = dict(_sections.player_state_of(next_state) or {})
        player_state["location_id"] = to_location
        next_state["player_state"] = player_state
        next_state["location_id"] = to_location

    visited = list(next_state.get("visited_locations") or [])
    if previous and previous not in visited:
        visited.append(previous)
    if to_location and to_location not in visited:
        visited.append(to_location)
    next_state["visited_locations"] = visited

    tick = int(next_state.get("tick") or 0)
    next_state["tick"] = tick + int(travel_result.get("travel_time_ticks") or 1)

    return next_state
