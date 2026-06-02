def test_ci_phase4_world_event_state_records_source_backed_local_events():
    from app.rpg.locations import RUSTY_FLAGON, ensure_world_event_state, record_world_event

    state = {}
    initial = ensure_world_event_state(state)
    recorded = record_world_event(
        state,
        location_id=RUSTY_FLAGON,
        event_id="event:bran:road_warning",
        kind="npc_warning",
        summary="Bran warns travelers that the old road is tense.",
        turn_index=1,
        source_detail="test_fixture",
    )

    assert initial["source"] == "deterministic_phase4_world_events"
    assert recorded["ok"] is True
    assert recorded["reason"] == "world_event_recorded"
    assert recorded["event"]["source"] == "deterministic_phase4_world_events"
    assert state["world_event_state"]["events"] == [recorded["event"]]
    assert state["world_event_state"]["last_event"] == recorded["event"]


def test_ci_phase4_world_event_unknown_location_is_rejected_without_invention():
    from app.rpg.locations import record_world_event

    result = record_world_event(
        {},
        location_id="location:missing",
        event_id="event:missing",
        summary="Missing.",
        turn_index=1,
    )

    assert result == {
        "ok": False,
        "reason": "unknown_location",
        "location_id": "location:missing",
        "source": "deterministic_phase4_world_events",
    }


def test_ci_phase4_derive_world_events_from_travel_encounter_and_discovery_logs():
    from app.rpg.locations import (
        OLD_MILL,
        OLD_ROAD,
        RUSTY_FLAGON,
        derive_world_events_from_logs,
        discover_location,
        record_encounter,
        roll_seeded_encounter,
    )
    from app.rpg.locations.travel import apply_travel

    state = {}
    apply_travel(state, start_location_id=RUSTY_FLAGON, end_location_id=OLD_ROAD, turn_index=1)
    record_encounter(state, roll_seeded_encounter("events", 2, location_id=OLD_ROAD), turn_index=2)
    discover_location(state, location_id=OLD_MILL, reason="scouted_old_road", turn_index=3)
    derived = derive_world_events_from_logs(state)
    kinds = {row["kind"] for row in derived["events"]}
    locations = {row["location_id"] for row in derived["events"]}

    assert derived["ok"] is True
    assert derived["reason"] == "world_events_derived"
    assert "travel_arrival" in kinds
    assert any(kind.startswith("encounter:") for kind in kinds)
    assert "location_discovered" in kinds
    assert OLD_ROAD in locations
    assert OLD_MILL in locations
    assert all(row["source"] == "deterministic_phase4_world_events" for row in derived["events"])


def test_ci_phase4_location_history_model_groups_events_by_canonical_location():
    from app.rpg.locations import (
        OLD_ROAD,
        RUSTY_FLAGON,
        build_location_history_model,
        record_world_event,
        roll_seeded_encounter,
        record_encounter,
    )
    from app.rpg.locations.travel import apply_travel

    state = {}
    record_world_event(
        state,
        location_id=RUSTY_FLAGON,
        event_id="event:tavern:rumor",
        kind="rumor",
        summary="A road rumor spreads through the tavern.",
        turn_index=0,
        source_detail="test_fixture",
    )
    apply_travel(state, start_location_id=RUSTY_FLAGON, end_location_id=OLD_ROAD, turn_index=1)
    record_encounter(state, roll_seeded_encounter("history", 2, location_id=OLD_ROAD), turn_index=2)
    model = build_location_history_model(state)
    by_id = {row["location_id"]: row for row in model["locations"]}

    assert model["source"] == "deterministic_phase4_location_history_report"
    assert model["event_count"] == 3
    assert RUSTY_FLAGON in by_id
    assert OLD_ROAD in by_id
    assert by_id[RUSTY_FLAGON]["events"][0]["event_id"] == "event:tavern:rumor"
    assert len(by_id[OLD_ROAD]["events"]) == 2


def test_ci_phase4_location_history_report_html_is_escaped_and_source_backed():
    from app.rpg.locations import RUSTY_FLAGON, record_world_event, render_location_history_report_html

    state = {}
    record_world_event(
        state,
        location_id=RUSTY_FLAGON,
        event_id="event:unsafe",
        kind="rumor",
        summary="Saw <script>bad</script> near the road.",
        turn_index=1,
        source_detail="<unsafe>",
    )
    html = render_location_history_report_html(state)

    assert "Location History" in html
    assert "The Rusty Flagon" in html
    assert "&lt;script&gt;bad&lt;/script&gt;" in html
    assert "<script>bad</script>" not in html
    assert "deterministic_phase4_location_history_report" in html


def test_ci_phase4_world_event_narration_contract_limits_claims():
    from app.rpg.locations import RUSTY_FLAGON, build_world_event_narration_contract, record_world_event

    result = record_world_event(
        {},
        location_id=RUSTY_FLAGON,
        event_id="event:bran:warning",
        kind="npc_warning",
        summary="Bran warns about road danger.",
        turn_index=1,
    )
    contract = build_world_event_narration_contract(result)

    assert contract["source"] == "deterministic_phase4_world_events"
    assert "Local world event: location:rusty_flagon — npc_warning — Bran warns about road danger." in contract[
        "allowed_world_event_claims"
    ]
    assert "Do not invent local events that are not in the deterministic world-event or derived history rows." in contract[
        "forbidden_world_event_claims"
    ]
    assert "Do not claim route access, combat results, rewards, inventory changes, XP, or quest progress changed from world events alone." in contract[
        "forbidden_world_event_claims"
    ]


def test_ci_phase4_world_event_readiness_and_exports():
    from app.rpg import locations

    readiness = locations.assert_phase4_world_events_location_history_ready()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase4_world_events_location_history_ready"
    assert readiness["blockers"] == []
    assert locations.ensure_world_event_state
    assert locations.record_world_event
    assert locations.derive_world_events_from_logs
    assert locations.build_location_history_model
    assert locations.render_location_history_report_html
    assert locations.build_world_event_narration_contract
