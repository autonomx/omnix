def test_ci_phase4_map_location_report_builds_initial_panel_payload():
    from app.rpg.locations import RUSTY_FLAGON, build_map_location_panel_payload

    state = {}
    payload = build_map_location_panel_payload(state)

    assert payload["source"] == "deterministic_phase4_map_location_report"
    assert payload["current_location_id"] == RUSTY_FLAGON
    assert payload["current_location"]["name"] == "The Rusty Flagon"
    assert payload["visible_exits"]
    assert {row["destination_id"] for row in payload["visible_exits"]} == {"location:old_road", "location:market"}
    assert all(row["source"] == "deterministic_phase4_map_location_report" for row in payload["visible_exits"])
    assert payload["time_state"]["clock_time"] == "08:00"
    assert payload["location_history"]["source"] == "deterministic_phase4_location_history_report"


def test_ci_phase4_map_location_report_reflects_travel_and_blocks():
    from app.rpg.locations import (
        OLD_MILL,
        OLD_ROAD,
        RUSTY_FLAGON,
        apply_travel,
        build_map_location_panel_payload,
        discover_location,
        discover_route,
    )

    state = {}
    discover_location(state, location_id=OLD_MILL, reason="scouted_old_road", turn_index=2)
    discover_route(state, edge_id="route:old_road:old_mill", reason="scouted_old_road", turn_index=2)
    travel = apply_travel(state, start_location_id=RUSTY_FLAGON, end_location_id=OLD_ROAD, turn_index=3)
    payload = build_map_location_panel_payload(state)

    assert travel["ok"] is True
    assert payload["current_location_id"] == OLD_ROAD
    old_mill_exit = next(row for row in payload["visible_exits"] if row["destination_id"] == OLD_MILL)
    assert old_mill_exit["discovered"] is True
    assert old_mill_exit["blocked"] is True
    assert old_mill_exit["block_reason"] == "bandit_threat_unresolved"
    assert payload["location_history"]["event_count"] >= 1


def test_ci_phase4_map_location_report_renders_escaped_html():
    from app.rpg.locations import build_map_location_panel_payload, render_map_location_report_html

    state = {}
    payload = build_map_location_panel_payload(state)
    payload["current_location"]["name"] = "<Rusty & Flagon>"
    html = render_map_location_report_html(payload)

    assert "Map & Location" in html
    assert "&lt;Rusty &amp; Flagon&gt;" in html
    assert "Visible exits" in html
    assert "deterministic_phase4_map_location_report" in html
    assert "<Rusty & Flagon>" not in html


def test_ci_phase4_map_location_report_contract_limits_claims():
    from app.rpg.locations import build_map_location_narration_contract, build_map_location_panel_payload

    payload = build_map_location_panel_payload({})
    contract = build_map_location_narration_contract(payload)

    assert contract["source"] == "deterministic_phase4_map_location_report"
    assert any("Current location: location:rusty_flagon" in row for row in contract["allowed_map_location_claims"])
    assert any("Visible exit:" in row for row in contract["allowed_map_location_claims"])
    assert "Do not invent locations, exits, route blocks, services, NPCs, hazards, or map state." in contract[
        "forbidden_map_location_claims"
    ]
    assert any("Do not reveal undiscovered destinations" in row for row in contract["forbidden_map_location_claims"])


def test_ci_phase4_map_location_report_readiness_and_exports():
    from app.rpg import locations

    readiness = locations.assert_phase4_map_location_report_ready()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase4_map_location_report_ready"
    assert readiness["blockers"] == []
    assert readiness["source"] == "deterministic_phase4_map_location_report"
    assert locations.build_map_location_panel_payload
    assert locations.render_map_location_report_html
    assert locations.build_map_location_narration_contract
