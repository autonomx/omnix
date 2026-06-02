from copy import deepcopy


def test_ci_phase4_campaign_report_map_location_panel_helper_renders_without_mutating_state():
    from app.rpg.locations import OLD_MILL, OLD_ROAD, RUSTY_FLAGON, apply_travel, discover_location, discover_route
    from tests.rpg.autoplay.campaign_report import render_phase4_campaign_report_map_location_panel

    state = {}
    discover_location(state, location_id=OLD_MILL, reason="scouted_old_road", turn_index=2)
    discover_route(state, edge_id="route:old_road:old_mill", reason="scouted_old_road", turn_index=2)
    travel = apply_travel(state, start_location_id=RUSTY_FLAGON, end_location_id=OLD_ROAD, turn_index=3)
    before = deepcopy(state)

    html = render_phase4_campaign_report_map_location_panel(simulation_state=state)

    assert travel["ok"] is True
    assert state == before
    assert "id=\"map-location-panel\"" in html
    assert "Map & Location" in html
    assert "Old Road" in html
    assert "Old Mill" in html
    assert "blocked" in html
    assert "bandit_threat_unresolved" in html
    assert "Time: Day" in html
    assert "deterministic_phase4_map_location_report" in html


def test_ci_phase4_campaign_report_map_location_panel_does_not_reveal_undiscovered_known_by_default():
    from app.rpg.locations import OLD_MILL, RUSTY_FLAGON, build_map_location_panel_payload
    from tests.rpg.autoplay.campaign_report import render_phase4_campaign_report_map_location_panel

    state = {}
    before = deepcopy(state)
    html = render_phase4_campaign_report_map_location_panel(simulation_state=state)
    panel = build_map_location_panel_payload(deepcopy(state))

    assert state == before
    assert "The Rusty Flagon" in html
    assert "Old Road" in html
    assert "Market" in html
    assert "Old Mill" not in html
    assert OLD_MILL not in {row["destination_id"] for row in panel["visible_exits"]}
    assert panel["current_location_id"] == RUSTY_FLAGON


def test_ci_phase4_campaign_report_html_append_is_idempotent_and_non_mutating():
    from app.rpg.locations import OLD_ROAD, RUSTY_FLAGON, apply_travel
    from tests.rpg.autoplay.campaign_report import append_phase4_map_location_panel_to_campaign_report_html

    state = {}
    apply_travel(state, start_location_id=RUSTY_FLAGON, end_location_id=OLD_ROAD, turn_index=1)
    before = deepcopy(state)

    html = append_phase4_map_location_panel_to_campaign_report_html(
        "<html><body><main><h1>Campaign Report</h1></main></body></html>",
        simulation_state=state,
    )
    html_again = append_phase4_map_location_panel_to_campaign_report_html(
        html,
        simulation_state=state,
    )

    assert state == before
    assert html == html_again
    assert html.count("id=\"map-location-panel\"") == 1
    assert "Campaign Report" in html
    assert "Old Road" in html
    assert "</main>" in html


def test_ci_phase4_campaign_report_renderer_includes_map_location_when_public_renderer_available():
    from tests.rpg.autoplay.campaign_report import render_campaign_report_html

    html = render_campaign_report_html({"simulation_state": {}})

    assert "id=\"map-location-panel\"" in html
    assert "Map & Location" in html
    assert "The Rusty Flagon" in html
    assert "deterministic_phase4_map_location_report" in html
