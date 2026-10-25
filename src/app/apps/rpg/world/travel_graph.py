# N82-N84 — Travel Graph + Location Progression v1

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Tuple
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


# Words of route labels and place names that say nothing about where a route goes ("travel to X").


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
