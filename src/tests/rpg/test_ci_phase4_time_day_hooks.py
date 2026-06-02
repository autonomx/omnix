def test_ci_phase4_time_day_hooks_initializes_deterministically():
    from app.rpg.locations import ensure_time_state

    state = {}
    time_state = ensure_time_state(state)

    assert state["time_state"] is time_state
    assert time_state["elapsed_minutes"] == 0
    assert time_state["day_count"] == 1
    assert time_state["minute_of_day"] == 480
    assert time_state["hour"] == 8
    assert time_state["clock_time"] == "08:00"
    assert time_state["time_of_day_label"] == "Morning"
    assert time_state["season"] == "early_autumn"
    assert time_state["weather_id"] != "weather:unset"
    assert time_state["weather_label"]
    assert time_state["weather_source"] == "deterministic_phase4_season_weather_expansion"
    assert time_state["time_log"] == []
    assert time_state["source"] == "deterministic_phase4_time_day_hooks"


def test_ci_phase4_time_day_hooks_labels_are_deterministic():
    from app.rpg.locations import describe_time_of_day, format_clock_time

    assert describe_time_of_day(5 * 60) == "Dawn"
    assert describe_time_of_day(8 * 60) == "Morning"
    assert describe_time_of_day(12 * 60) == "Afternoon"
    assert describe_time_of_day(17 * 60) == "Evening"
    assert describe_time_of_day(21 * 60) == "Night"
    assert describe_time_of_day(4 * 60 + 59) == "Night"
    assert format_clock_time(0) == "00:00"
    assert format_clock_time(23 * 60 + 59) == "23:59"
    assert format_clock_time(24 * 60 + 5) == "00:05"


def test_ci_phase4_time_day_hooks_advance_minutes_and_day_count():
    from app.rpg.locations import advance_time

    state = {}
    first = advance_time(state, 55, reason="travel", turn_index=7)
    crossing = advance_time(state, 24 * 60, reason="overnight_wait", turn_index=8)

    assert first["ok"] is True
    assert first["reason"] == "time_advanced"
    assert first["before"]["clock_time"] == "08:00"
    assert first["after"]["clock_time"] == "08:55"
    assert first["after"]["day_count"] == 1
    assert first["after"]["weather_id"] != "weather:unset"
    assert first["time_log_entry"] == {
        "turn_index": 7,
        "minutes": 55,
        "reason": "travel",
        "before_day_count": 1,
        "after_day_count": 1,
        "source": "deterministic_phase4_time_day_hooks",
    }
    assert crossing["ok"] is True
    assert crossing["after"]["day_count"] == 2
    assert crossing["after"]["clock_time"] == "08:55"
    assert len(state["time_state"]["time_log"]) == 2


def test_ci_phase4_time_day_hooks_apply_old_mill_travel_time():
    from app.rpg.locations import OLD_MILL, RUSTY_FLAGON, apply_travel, apply_travel_time

    state = {}
    travel = apply_travel(state, start_location_id=RUSTY_FLAGON, end_location_id=OLD_MILL, turn_index=3)
    applied = apply_travel_time(state, travel, turn_index=3)

    assert travel["ok"] is True
    assert travel["travel_log_entry"]["minutes"] == 55
    assert applied["ok"] is True
    assert applied["reason"] == "travel_time_applied"
    assert applied["travel_minutes"] == 55
    assert applied["after"]["elapsed_minutes"] == 55
    assert applied["after"]["clock_time"] == "08:55"
    assert applied["after"]["time_of_day_label"] == "Morning"
    assert applied["after"]["weather_source"] == "deterministic_phase4_season_weather_expansion"
    assert applied["source"] == "deterministic_phase4_time_day_hooks"


def test_ci_phase4_time_day_hooks_reject_invalid_advances_safely():
    from app.rpg.locations import advance_time, apply_travel_time

    state = {}
    before = dict(state)
    invalid = advance_time(state, 0, reason="invalid", turn_index=1)
    no_travel = apply_travel_time(state, {"ok": False, "reason": "route_blocked"}, turn_index=1)
    missing_minutes = apply_travel_time(state, {"ok": True, "travel_log_entry": {}}, turn_index=1)

    assert invalid["ok"] is False
    assert invalid["reason"] == "invalid_time_advance_minutes"
    assert invalid["source"] == "deterministic_phase4_time_day_hooks"
    assert state == before
    assert no_travel["ok"] is False
    assert no_travel["reason"] == "travel_time_not_applied"
    assert missing_minutes["ok"] is False
    assert missing_minutes["reason"] == "missing_travel_minutes"


def test_ci_phase4_time_day_hooks_narration_contract_forbids_invention():
    from app.rpg.locations import advance_time, build_time_narration_contract

    result = advance_time({}, 55, reason="travel", turn_index=2)
    contract = build_time_narration_contract(result)

    assert contract["source"] == "deterministic_phase4_time_day_hooks"
    assert "Day count: 1" in contract["allowed_time_claims"]
    assert "Clock time: 08:55" in contract["allowed_time_claims"]
    assert "Time of day: Morning" in contract["allowed_time_claims"]
    assert "Elapsed minutes: 55" in contract["allowed_time_claims"]
    assert "Season: early_autumn" in contract["allowed_time_claims"]
    assert "Do not invent dates, calendar names, or time jumps." in contract["forbidden_time_claims"]
    assert "Only claim weather and season details present in the deterministic after time_state." in contract[
        "forbidden_time_claims"
    ]


def test_ci_phase4_time_day_hooks_readiness_and_exports():
    from app.rpg import locations

    readiness = locations.assert_phase4_time_day_hooks_ready()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase4_time_day_hooks_ready"
    assert readiness["blockers"] == []
    assert readiness["source"] == "deterministic_phase4_time_day_hooks"
    assert locations.ensure_time_state
    assert locations.advance_time
    assert locations.apply_travel_time
    assert locations.describe_time_of_day
    assert locations.build_time_narration_contract
