def test_ci_phase4_encounter_tables_are_deterministic_and_source_backed():
    from app.rpg.locations import ENCOUNTER_TABLES, OLD_ROAD, list_encounter_table

    first = list_encounter_table(location_id=OLD_ROAD)
    second = list_encounter_table(location_id=OLD_ROAD)

    assert first == second
    assert first["ok"] is True
    assert first["reason"] == "encounter_table_listed"
    assert first["table_key"] == OLD_ROAD
    assert first["encounters"] == ENCOUNTER_TABLES[OLD_ROAD]
    assert len(first["encounters"]) >= 2
    assert all(row["source"] == "deterministic_phase4_seeded_encounters" for row in first["encounters"])
    assert all(row["encounter_id"].startswith("encounter:") for row in first["encounters"])


def test_ci_phase4_same_seed_location_route_turn_returns_same_encounter():
    from app.rpg.locations import OLD_ROAD, roll_seeded_encounter

    first = roll_seeded_encounter("stable-seed", 7, location_id=OLD_ROAD)
    second = roll_seeded_encounter("stable-seed", 7, location_id=OLD_ROAD)

    assert first == second
    assert first["ok"] is True
    assert first["reason"] == "seeded_encounter_rolled"
    assert first["source"] == "deterministic_phase4_seeded_encounters"
    assert first["encounter"]["source"] == "deterministic_phase4_seeded_encounters"


def test_ci_phase4_different_route_stays_bounded_to_route_table():
    from app.rpg.locations import ENCOUNTER_TABLES, OLD_ROAD, roll_seeded_encounter

    location_result = roll_seeded_encounter("phase4", 5, location_id=OLD_ROAD)
    route_result = roll_seeded_encounter("phase4", 5, edge_id="route:old_road:old_mill")
    route_ids = {row["encounter_id"] for row in ENCOUNTER_TABLES["route:old_road:old_mill"]}
    location_ids = {row["encounter_id"] for row in ENCOUNTER_TABLES[OLD_ROAD]}

    assert location_result["encounter"]["encounter_id"] in location_ids
    assert route_result["encounter"]["encounter_id"] in route_ids
    assert route_result["table_key"] == "route:old_road:old_mill"
    assert route_result["edge_id"] == "route:old_road:old_mill"


def test_ci_phase4_unknown_location_or_route_returns_safe_rejection():
    from app.rpg.locations import list_encounter_table, roll_seeded_encounter

    unknown_location = roll_seeded_encounter("seed", 1, location_id="location:missing")
    unknown_route = list_encounter_table(edge_id="route:missing")

    assert unknown_location == {
        "ok": False,
        "reason": "unknown_location",
        "location_id": "location:missing",
        "encounters": [],
        "source": "deterministic_phase4_seeded_encounters",
    }
    assert unknown_route == {
        "ok": False,
        "reason": "unknown_route",
        "edge_id": "route:missing",
        "encounters": [],
        "source": "deterministic_phase4_seeded_encounters",
    }


def test_ci_phase4_record_encounter_appends_log_without_mutating_player_or_combat_state():
    from app.rpg.locations import OLD_ROAD, ensure_encounter_state, record_encounter, roll_seeded_encounter

    state = {"player_state": {"hp": 12, "xp": 0}, "combat_state": {"active": False}}
    result = roll_seeded_encounter("log-seed", 4, location_id=OLD_ROAD)
    recorded = record_encounter(state, result, turn_index=4)
    encounter_state = ensure_encounter_state(state)

    assert recorded["ok"] is True
    assert recorded["reason"] == "encounter_recorded"
    assert len(encounter_state["encounter_log"]) == 1
    assert encounter_state["last_encounter"] == encounter_state["encounter_log"][0]
    assert encounter_state["encounter_log"][0]["source"] == "deterministic_phase4_seeded_encounters"
    assert state["player_state"] == {"hp": 12, "xp": 0}
    assert state["combat_state"] == {"active": False}


def test_ci_phase4_encounter_narration_contract_forbids_invented_outcomes():
    from app.rpg.locations import OLD_ROAD, build_encounter_narration_contract, roll_seeded_encounter

    result = roll_seeded_encounter("contract-seed", 6, location_id=OLD_ROAD)
    contract = build_encounter_narration_contract(result)

    assert contract["source"] == "deterministic_phase4_seeded_encounters"
    assert f"Encounter id: {result['encounter']['encounter_id']}" in contract["allowed_encounter_claims"]
    assert f"Encounter kind: {result['encounter']['kind']}" in contract["allowed_encounter_claims"]
    assert "Do not invent enemies, rewards, locations, route access, or combat outcomes." in contract[
        "forbidden_encounter_claims"
    ]
    assert "Do not start combat or apply damage unless a later deterministic combat bridge does so." in contract[
        "forbidden_encounter_claims"
    ]
    assert "Do not claim items, currency, XP, quest state, discovery state, or survival resources changed." in contract[
        "forbidden_encounter_claims"
    ]


def test_ci_phase4_seeded_encounter_readiness_and_exports():
    from app.rpg import locations

    readiness = locations.assert_phase4_seeded_encounters_ready()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase4_seeded_encounters_ready"
    assert readiness["blockers"] == []
    assert locations.ENCOUNTER_TABLES
    assert locations.ensure_encounter_state
    assert locations.list_encounter_table
    assert locations.roll_seeded_encounter
    assert locations.record_encounter
    assert locations.build_encounter_narration_contract
