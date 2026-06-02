def test_ci_phase4_location_graph_validates_canonical_locations_and_edges():
    from app.rpg.locations import (
        MARKET,
        NEARBY_WILDERNESS,
        OLD_MILL,
        OLD_ROAD,
        RUSTY_FLAGON,
        SOURCE,
        list_canonical_locations,
        validate_location_graph,
    )

    validation = validate_location_graph()
    locations = list_canonical_locations()
    location_ids = [location["location_id"] for location in locations]

    assert validation["ok"] is True
    assert validation["reason"] == "location_graph_valid"
    assert validation["source"] == SOURCE
    assert validation["location_count"] == 5
    assert validation["edge_count"] == 5
    assert validation["blockers"] == []
    assert location_ids == [RUSTY_FLAGON, MARKET, OLD_ROAD, OLD_MILL, NEARBY_WILDERNESS]
    assert all(location["source"] == SOURCE for location in locations)
    assert all(location["name"] and location["description"] for location in locations)


def test_ci_phase4_location_graph_exposes_services_npcs_hazards_and_exits():
    from app.rpg.locations import OLD_MILL, OLD_ROAD, RUSTY_FLAGON, get_canonical_location, list_location_exits

    tavern = get_canonical_location(RUSTY_FLAGON)
    old_road = get_canonical_location(OLD_ROAD)
    old_mill = get_canonical_location(OLD_MILL)
    tavern_exits = list_location_exits(RUSTY_FLAGON)

    assert tavern["services"] == ["service:inn_room", "service:tavern_meal", "service:rumors"]
    assert tavern["npcs"] == ["npc:bran"]
    assert tavern["hazards"] == []
    assert "hazard:bandit_ambush_risk" in old_road["hazards"]
    assert old_mill["npcs"] == ["npc:bandit_leader"]
    assert "hazard:bandit_camp" in old_mill["hazards"]
    assert [exit_row["destination_id"] for exit_row in tavern_exits] == [OLD_ROAD, "location:market"]
    assert all(exit_row["source"] == "deterministic_phase4_location_graph" for exit_row in tavern_exits)


def test_ci_phase4_location_graph_finds_required_rusty_flagon_old_mill_path():
    from app.rpg.locations import OLD_MILL, OLD_ROAD, RUSTY_FLAGON, assert_phase4_location_graph_ready, find_location_route

    route = find_location_route(RUSTY_FLAGON, OLD_MILL)
    readiness = assert_phase4_location_graph_ready()

    assert route["ok"] is True
    assert route["reason"] == "route_found"
    assert route["path"] == [RUSTY_FLAGON, OLD_ROAD, OLD_MILL]
    assert [edge["edge_id"] for edge in route["edges"]] == [
        "route:rusty_flagon:old_road",
        "route:old_road:old_mill",
    ]
    assert readiness["ok"] is True
    assert readiness["reason"] == "phase4_location_graph_ready"
    assert readiness["blockers"] == []


def test_ci_phase4_location_graph_rejects_unknown_locations_without_llm_guessing():
    from app.rpg.locations import OLD_MILL, find_location_route, get_canonical_location, list_location_exits

    route = find_location_route("location:imagined_castle", OLD_MILL)

    assert get_canonical_location("location:imagined_castle") is None
    assert list_location_exits("location:imagined_castle") == []
    assert route["ok"] is False
    assert route["reason"] == "unknown_location"
    assert route["unknown_locations"] == ["location:imagined_castle"]
    assert route["source"] == "deterministic_phase4_location_graph"


def test_ci_phase4_location_graph_builds_source_backed_map_and_narration_contract():
    from app.rpg.locations import OLD_ROAD, RUSTY_FLAGON, build_location_map_payload, build_location_narration_contract

    payload = build_location_map_payload(RUSTY_FLAGON)
    contract = build_location_narration_contract(payload)

    assert payload["source"] == "deterministic_phase4_location_graph"
    assert payload["current_location_id"] == RUSTY_FLAGON
    assert payload["current_location"]["name"] == "The Rusty Flagon"
    assert payload["validation"]["ok"] is True
    assert [exit_row["destination_id"] for exit_row in payload["visible_exits"]] == [OLD_ROAD, "location:market"]
    assert contract["source"] == "deterministic_phase4_location_graph"
    assert "Known location: location:old_mill — Old Mill" in contract["allowed_location_claims"]
    assert "Known route: location:old_road -> location:old_mill" in contract["allowed_location_claims"]
    assert "Do not invent locations that are not in the location graph." in contract["forbidden_location_claims"]


def test_ci_phase4_location_helpers_are_exported():
    from app.rpg import locations

    assert locations.build_location_map_payload
    assert locations.find_location_route
    assert locations.assert_phase4_location_graph_ready
