from __future__ import annotations

import pytest

from app.rpg.world_runtime import WORLD_RUNTIME_SOURCE, build_world_runtime_report, graph_from_state


def _state() -> dict[str, object]:
    return {
        "world": {},
        "player": {"location_id": "tavern"},
        "inventory": {},
        "quests": {},
        "npcs": {},
        "map": {
            "locations": {
                "tavern": {"name": "Rusty Flagon", "status": "expanded", "services": ["inn"]},
                "market": {"name": "Market", "status": "expanded", "services": ["shop"]},
                "quarry": {"name": "Old Quarry", "status": "stub"},
            },
            "routes": [
                {"id": "route:tavern-market", "from_id": "tavern", "to_id": "market", "status": "open", "safe": True},
                {"id": "route:tavern-quarry", "from_id": "tavern", "to_id": "quarry", "status": "open", "safe": True},
            ],
        },
    }


def test_world_runtime_report_allows_safe_known_travel() -> None:
    report = build_world_runtime_report(
        {"simulation_state": _state(), "target_location_id": "market"},
    )

    assert report["source"] == WORLD_RUNTIME_SOURCE
    assert report["ready"] is True
    assert report["travel"]["ok"] is True
    assert report["travel"]["route_id"] == "route:tavern-market"
    assert report["map_debug"]["current_location_id"] == "tavern"
    assert "quarry" in report["map_debug"]["discoverable_stubs"]


def test_world_runtime_report_flags_stub_target() -> None:
    report = build_world_runtime_report(
        {"simulation_state": _state(), "target_location_id": "quarry"},
    )

    assert report["ready"] is False
    assert "travel_not_instant:target_requires_expansion" in report["issues"]


def test_graph_from_state_parses_location_mapping() -> None:
    graph = graph_from_state(_state())

    assert graph.get_location("market").services == ("shop",)
    assert graph.known_exits("tavern") == ("market", "quarry")
    assert graph.get_route("route:tavern-market").status == "open"


def test_graph_from_state_preserves_locked_and_direction() -> None:
    state = _state()
    state["map"]["routes"] = [
        {
            "id": "route:market-exit",
            "from_id": "market",
            "to_id": "tavern",
            "status": "locked",
            "direction": "forward",
        }
    ]

    route = graph_from_state(state).get_route("route:market-exit")

    assert route.status == "locked"
    assert route.direction == "forward"


def test_graph_from_state_rejects_unknown_route_status() -> None:
    state = _state()
    state["map"]["routes"] = [
        {"id": "route:future", "from_id": "tavern", "to_id": "market", "status": "phased"}
    ]

    with pytest.raises(ValueError, match="unsupported_route_status:phased"):
        graph_from_state(state)


def test_world_runtime_does_not_fabricate_missing_current_location() -> None:
    state = _state()
    state["player"] = {}

    report = build_world_runtime_report({"simulation_state": state})

    assert report["ready"] is False
    assert report["current_location_id"] == ""
    assert report["map_debug"] is None
    assert "missing_current_location" in report["issues"]
