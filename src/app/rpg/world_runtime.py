"""Runtime world graph, travel, and map report adapters for RPG Phase 19."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.rpg.world_graph import (
    RouteDirection,
    RouteStatus,
    RpgLocationNode,
    RpgRegionGraph,
    RpgRoute,
    can_instant_travel,
    map_debug_payload,
)

WORLD_RUNTIME_SOURCE = "phase19_world_runtime_v1"
_REQUIRED_SAVE_GROUPS = ("world", "map", "player", "inventory", "quests", "npcs")
_ROUTE_STATUSES = {"open", "blocked", "locked"}
_ROUTE_DIRECTIONS = {"both", "forward"}


def build_world_runtime_report(
    turn_result: Mapping[str, object],
    *,
    current_location_id: str | None = None,
    target_location_id: str | None = None,
) -> dict[str, object]:
    """Build a deterministic report for travel/map/save-load surfaces."""

    state = _mapping(turn_result.get("simulation_state") or turn_result.get("state"))
    graph = graph_from_state(state)
    current = current_location_id or _current_location_id(turn_result, state)
    target = target_location_id or _target_location_id(turn_result)
    travel = None
    if current and target:
        travel = can_instant_travel(graph, current, target).as_dict()
    save_groups = [key for key in _REQUIRED_SAVE_GROUPS if key in state]
    issues = tuple(_world_runtime_issues(state, graph, current, target, travel))
    return {
        "source": WORLD_RUNTIME_SOURCE,
        "ready": not issues,
        "issues": list(issues),
        "current_location_id": current,
        "target_location_id": target,
        "travel": travel,
        "map_debug": map_debug_payload(graph, current) if current else None,
        "save_load_groups_present": save_groups,
    }


def graph_from_state(state: Mapping[str, object]) -> RpgRegionGraph:
    """Parse a runtime map/world payload into the deterministic graph contract."""

    raw_map = _mapping(state.get("map") or state.get("world_map") or state.get("world"))
    raw_locations = raw_map.get("locations") or ()
    raw_routes = raw_map.get("routes") or ()
    locations: dict[str, RpgLocationNode] = {}
    for item in _iter_nodes(raw_locations):
        node = _location_node(item)
        locations[node.id] = node
    routes = tuple(
        _route(item, index)
        for index, item in enumerate(_sequence(raw_routes))
        if isinstance(item, Mapping)
    )
    return RpgRegionGraph(locations=locations, routes=routes)


def attach_world_runtime_to_row(row: Mapping[str, object]) -> dict[str, object]:
    result = dict(row)
    turn_result = _mapping(row.get("turn_result")) or row
    result["world_runtime"] = build_world_runtime_report(turn_result)
    return result


def _world_runtime_issues(
    state: Mapping[str, object],
    graph: RpgRegionGraph,
    current: str,
    target: str,
    travel: Mapping[str, object] | None,
) -> tuple[str, ...]:
    issues: list[str] = []
    for key in _REQUIRED_SAVE_GROUPS:
        if key not in state:
            issues.append(f"missing_save_group:{key}")
    if not graph.locations:
        issues.append("missing_map_locations")
    if not current:
        issues.append("missing_current_location")
    elif current not in graph.locations:
        issues.append("current_location_not_in_graph")
    if target and travel and travel.get("ok") is not True:
        issues.append(f"travel_not_instant:{travel.get('reason')}")
    return tuple(issues)


def _current_location_id(
    turn_result: Mapping[str, object],
    state: Mapping[str, object],
) -> str:
    for raw in (
        turn_result.get("current_location_id"),
        turn_result.get("location_id"),
        _mapping(state.get("player")).get("location_id"),
        state.get("current_location_id"),
    ):
        if raw:
            return str(raw)
    return ""


def _target_location_id(turn_result: Mapping[str, object]) -> str:
    for raw in (turn_result.get("target_location_id"), turn_result.get("travel_target_id")):
        if raw:
            return str(raw)
    return ""


def _iter_nodes(raw_locations: object) -> tuple[Mapping[str, object], ...]:
    if isinstance(raw_locations, Mapping):
        return tuple(
            {"id": key, **_mapping(value)} for key, value in raw_locations.items() if isinstance(value, Mapping)
        )
    return tuple(item for item in _sequence(raw_locations) if isinstance(item, Mapping))


def _location_node(raw: Mapping[str, object]) -> RpgLocationNode:
    return RpgLocationNode(
        id=str(raw.get("id") or raw.get("location_id") or "unknown"),
        name=str(raw.get("name") or raw.get("id") or "Unknown"),
        region_id=str(raw.get("region_id") or raw.get("region") or "runtime"),
        status="expanded" if str(raw.get("status") or "expanded") == "expanded" else "stub",
        tags=tuple(str(item) for item in _sequence(raw.get("tags"))),
        services=tuple(str(item) for item in _sequence(raw.get("services"))),
        danger=int(raw.get("danger") or 0),
    )


def _route(raw: Mapping[str, object], index: int) -> RpgRoute:
    from_id = str(raw.get("from_id") or raw.get("from") or "")
    to_id = str(raw.get("to_id") or raw.get("to") or "")
    status = _route_status(raw.get("status"))
    direction = _route_direction(raw.get("direction"))
    route_id = str(raw.get("id") or raw.get("route_id") or f"legacy-route:{from_id}:{to_id}:{index}")
    return RpgRoute(
        from_id=from_id,
        to_id=to_id,
        status=status,
        safe=bool(raw.get("safe", True)),
        known=bool(raw.get("known", True)),
        tags=tuple(str(item) for item in _sequence(raw.get("tags"))),
        id=route_id,
        direction=direction,
    )


def _route_status(value: object) -> RouteStatus:
    status = str(value or "open").strip().lower()
    if status not in _ROUTE_STATUSES:
        raise ValueError(f"unsupported_route_status:{status}")
    return status  # type: ignore[return-value]


def _route_direction(value: object) -> RouteDirection:
    direction = str(value or "both").strip().lower()
    if direction not in _ROUTE_DIRECTIONS:
        raise ValueError(f"unsupported_route_direction:{direction}")
    return direction  # type: ignore[return-value]


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return ()
