from __future__ import annotations

from app.rpg.world_graph import (
    RpgLocationNode,
    RpgRegionGraph,
    RpgRoute,
    can_instant_travel,
    map_debug_payload,
)


def _sample_graph() -> RpgRegionGraph:
    return RpgRegionGraph(
        locations={
            "tavern": RpgLocationNode("tavern", "Rusty Flagon", "vance", "expanded", services=("inn",)),
            "market": RpgLocationNode("market", "Market Row", "vance", "expanded", services=("shop",)),
            "quarry": RpgLocationNode("quarry", "Old Quarry", "north", "stub", tags=("bandit_rumor",)),
        },
        routes=(
            RpgRoute("tavern", "market", id="route:tavern-market"),
            RpgRoute("tavern", "quarry", safe=False, tags=("danger",), id="route:tavern-quarry"),
        ),
    )


def test_known_exits_and_discoverable_stubs_are_stable() -> None:
    graph = _sample_graph()

    assert graph.known_exits("tavern") == ("market", "quarry")
    assert [node.id for node in graph.discoverable_stubs("tavern")] == ["quarry"]


def test_known_safe_expanded_route_allows_instant_travel() -> None:
    result = can_instant_travel(_sample_graph(), "tavern", "market")

    assert result.ok is True
    assert result.mode == "instant"
    assert result.requires_narration is False
    assert result.reason == "known_safe_route"
    assert result.route_id == "route:tavern-market"


def test_stub_or_unsafe_route_requires_narration_and_resolution() -> None:
    result = can_instant_travel(_sample_graph(), "tavern", "quarry")

    assert result.ok is False
    assert result.mode == "blocked"
    assert result.requires_narration is True
    assert result.reason == "route_requires_encounter_check"


def test_graph_updates_are_pure() -> None:
    graph = _sample_graph()
    expanded_quarry = graph.locations["quarry"].expanded(tags=("stone",), danger=3)
    updated = graph.with_location(expanded_quarry)

    assert graph.locations["quarry"].status == "stub"
    assert updated.locations["quarry"].status == "expanded"
    assert updated.locations["quarry"].danger == 3


def test_route_updates_replace_by_id_not_endpoint_pair() -> None:
    graph = _sample_graph().with_route(
        RpgRoute("tavern", "market", safe=False, id="route:tavern-market:forest")
    )
    replaced = graph.with_route(
        RpgRoute("tavern", "market", status="locked", id="route:tavern-market")
    )

    assert [route.id for route in graph.routes_between("tavern", "market")] == [
        "route:tavern-market",
        "route:tavern-market:forest",
    ]
    assert replaced.get_route("route:tavern-market").status == "locked"
    assert replaced.get_route("route:tavern-market:forest").safe is False


def test_forward_route_does_not_create_reverse_exit() -> None:
    graph = RpgRegionGraph(
        locations=_sample_graph().locations,
        routes=(RpgRoute("tavern", "market", id="route:one-way", direction="forward"),),
    )

    assert graph.known_exits("tavern") == ("market",)
    assert graph.known_exits("market") == ()
    assert can_instant_travel(graph, "market", "tavern").reason == "route_unknown"


def test_locked_route_status_is_preserved_in_travel_result() -> None:
    graph = _sample_graph().with_route(
        RpgRoute("tavern", "market", status="locked", id="route:tavern-market")
    )

    result = can_instant_travel(graph, "tavern", "market", route_id="route:tavern-market")

    assert result.ok is False
    assert result.reason == "route_locked"
    assert result.route_id == "route:tavern-market"


def test_legacy_route_constructor_derives_stable_id() -> None:
    assert RpgRoute("tavern", "market").id == "route:tavern:market"


def test_map_debug_payload_is_report_friendly() -> None:
    payload = map_debug_payload(_sample_graph(), "tavern")

    assert payload["current_location_id"] == "tavern"
    assert payload["known_exits"] == ["market", "quarry"]
    assert payload["discoverable_stubs"] == ["quarry"]
    assert payload["routes"] == ["route:tavern-market", "route:tavern-quarry"]
    assert payload["route_count"] == 2
