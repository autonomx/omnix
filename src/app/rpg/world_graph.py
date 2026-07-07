"""Deterministic RPG world graph and location stub helpers."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal, Mapping, Sequence

LocationStatus = Literal["stub", "expanded"]
RouteStatus = Literal["open", "blocked", "locked"]
RouteDirection = Literal["both", "forward"]
TravelMode = Literal["instant", "blocked", "unknown"]


@dataclass(frozen=True)
class RpgLocationNode:
    id: str
    name: str
    region_id: str
    status: LocationStatus = "stub"
    tags: tuple[str, ...] = ()
    services: tuple[str, ...] = ()
    danger: int = 0

    def expanded(self, *, tags: Sequence[str] = (), services: Sequence[str] = (), danger: int | None = None) -> "RpgLocationNode":
        return replace(
            self,
            status="expanded",
            tags=tuple(tags) or self.tags,
            services=tuple(services) or self.services,
            danger=self.danger if danger is None else danger,
        )


@dataclass(frozen=True)
class RpgRoute:
    """Canonical route with backward-compatible legacy ID derivation.

    `id` and `direction` are trailing fields so older positional construction remains
    readable while persisted/new map data supplies explicit stable IDs.
    """

    from_id: str
    to_id: str
    status: RouteStatus = "open"
    safe: bool = True
    known: bool = True
    tags: tuple[str, ...] = ()
    id: str = ""
    direction: RouteDirection = "both"

    def __post_init__(self) -> None:
        if not self.from_id or not self.to_id:
            raise ValueError("route_endpoint_missing")
        if self.status not in {"open", "blocked", "locked"}:
            raise ValueError(f"unsupported_route_status:{self.status}")
        if self.direction not in {"both", "forward"}:
            raise ValueError(f"unsupported_route_direction:{self.direction}")
        if not self.id:
            legacy_id = f"route:{self.from_id}:{self.to_id}"
            object.__setattr__(self, "id", legacy_id)

    def connects(self, location_id: str, target_id: str) -> bool:
        return {self.from_id, self.to_id} == {location_id, target_id}

    def allows(self, location_id: str, target_id: str) -> bool:
        if self.from_id == location_id and self.to_id == target_id:
            return True
        return self.direction == "both" and self.to_id == location_id and self.from_id == target_id

    def other(self, location_id: str) -> str | None:
        if self.from_id == location_id:
            return self.to_id
        if self.direction == "both" and self.to_id == location_id:
            return self.from_id
        return None


@dataclass(frozen=True)
class RpgTravelResult:
    ok: bool
    from_id: str
    to_id: str
    mode: TravelMode
    reason: str
    requires_narration: bool = False
    route_id: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "from_id": self.from_id,
            "to_id": self.to_id,
            "mode": self.mode,
            "reason": self.reason,
            "requires_narration": self.requires_narration,
            "route_id": self.route_id,
        }


@dataclass(frozen=True)
class RpgRegionGraph:
    locations: Mapping[str, RpgLocationNode] = field(default_factory=dict)
    routes: tuple[RpgRoute, ...] = ()

    def get_location(self, location_id: str) -> RpgLocationNode | None:
        return self.locations.get(location_id)

    def get_route(self, route_id: str) -> RpgRoute | None:
        return next((route for route in self.routes if route.id == route_id), None)

    def known_exits(self, location_id: str) -> tuple[str, ...]:
        exits = {
            other
            for route in self.routes
            if route.known and (other := route.other(location_id)) is not None
        }
        return tuple(sorted(exits))

    def discoverable_stubs(self, location_id: str) -> tuple[RpgLocationNode, ...]:
        stubs = []
        for target_id in self.known_exits(location_id):
            target = self.get_location(target_id)
            if target and target.status == "stub":
                stubs.append(target)
        return tuple(sorted(stubs, key=lambda node: node.id))

    def routes_between(self, location_id: str, target_id: str) -> tuple[RpgRoute, ...]:
        return tuple(
            sorted(
                (route for route in self.routes if route.allows(location_id, target_id)),
                key=lambda route: route.id,
            )
        )

    def route_between(self, location_id: str, target_id: str) -> RpgRoute | None:
        routes = self.routes_between(location_id, target_id)
        return routes[0] if routes else None

    def with_location(self, node: RpgLocationNode) -> "RpgRegionGraph":
        updated = dict(self.locations)
        updated[node.id] = node
        return replace(self, locations=updated)

    def with_route(self, route: RpgRoute) -> "RpgRegionGraph":
        existing = [candidate for candidate in self.routes if candidate.id != route.id]
        return replace(self, routes=tuple(sorted((*existing, route), key=lambda item: item.id)))


def can_instant_travel(
    graph: RpgRegionGraph,
    location_id: str,
    target_id: str,
    *,
    route_id: str | None = None,
) -> RpgTravelResult:
    if location_id not in graph.locations:
        return RpgTravelResult(False, location_id, target_id, "unknown", "current_location_unknown", True, route_id)
    if target_id not in graph.locations:
        return RpgTravelResult(False, location_id, target_id, "unknown", "target_location_unknown", True, route_id)

    route = graph.get_route(route_id) if route_id else graph.route_between(location_id, target_id)
    if route is None or not route.known or not route.allows(location_id, target_id):
        return RpgTravelResult(False, location_id, target_id, "unknown", "route_unknown", True, route_id)
    if route.status != "open":
        return RpgTravelResult(False, location_id, target_id, "blocked", f"route_{route.status}", True, route.id)
    if not route.safe:
        return RpgTravelResult(False, location_id, target_id, "blocked", "route_requires_encounter_check", True, route.id)

    target = graph.get_location(target_id)
    if target and target.status == "stub":
        return RpgTravelResult(False, location_id, target_id, "blocked", "target_requires_expansion", True, route.id)
    return RpgTravelResult(True, location_id, target_id, "instant", "known_safe_route", False, route.id)


def map_debug_payload(graph: RpgRegionGraph, current_location_id: str) -> dict[str, object]:
    return {
        "current_location_id": current_location_id,
        "known_exits": list(graph.known_exits(current_location_id)),
        "discoverable_stubs": [node.id for node in graph.discoverable_stubs(current_location_id)],
        "locations": [node.id for node in sorted(graph.locations.values(), key=lambda item: item.id)],
        "routes": [route.id for route in sorted(graph.routes, key=lambda item: item.id)],
        "route_count": len(graph.routes),
    }
