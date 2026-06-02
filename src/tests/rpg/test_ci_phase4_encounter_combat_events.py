from copy import deepcopy


def _world_event_encounter():
    return {
        "ok": True,
        "location_id": "location:old_road",
        "encounter": {
            "encounter_id": "encounter:old_road:bandit_scout_tracks",
            "kind": "evidence",
            "summary": "Boot prints and snapped brush suggest a bandit scout crossed the road recently.",
            "tags": ["road", "tracks", "bandit_risk"],
            "source": "deterministic_phase4_seeded_encounters",
        },
        "source": "deterministic_phase4_seeded_encounters",
    }


def _combat_candidate_encounter():
    return {
        "ok": True,
        "edge_id": "route:old_road:old_mill",
        "encounter": {
            "encounter_id": "encounter:old_mill_route:bandit_patrol",
            "kind": "threat_signal",
            "summary": "A distant bandit patrol passes near the old mill route, not yet committing to combat.",
            "tags": ["route", "bandit_patrol", "combat_hook"],
            "source": "deterministic_phase4_seeded_encounters",
        },
        "source": "deterministic_phase4_seeded_encounters",
    }


def test_ci_phase4_encounter_runtime_records_non_combat_world_event():
    from app.rpg.locations import apply_seeded_encounter_runtime

    state = {}
    result = apply_seeded_encounter_runtime(state, _world_event_encounter(), turn_index=11)

    assert result["ok"] is True
    assert result["reason"] == "encounter_world_event_recorded"
    assert result["combat_candidate"] is None
    assert result["classification"]["kind"] == "world_event"
    event = result["world_event_result"]["event"]
    assert event["location_id"] == "location:old_road"
    assert event["event_id"] == "event:encounter:old_road:bandit_scout_tracks"
    assert event["kind"] == "encounter:evidence"
    assert event["source_detail"] == "deterministic_phase4_encounter_combat_events"
    assert state["world_event_state"]["last_event"] == event


def test_ci_phase4_encounter_runtime_no_encounter_is_noop():
    from app.rpg.locations import NO_ENCOUNTER, apply_seeded_encounter_runtime

    state = {"player_state": {"hp": 10}, "combat_state": {"active": False}}
    before = deepcopy(state)
    result = apply_seeded_encounter_runtime(
        state,
        {"ok": True, "location_id": "location:old_road", "encounter": {"encounter_id": NO_ENCOUNTER, "kind": "none"}},
        turn_index=12,
    )

    assert result["ok"] is True
    assert result["reason"] == "encounter_runtime_noop"
    assert result["classification"]["kind"] == "noop"
    assert state == before


def test_ci_phase4_encounter_runtime_combat_hook_returns_candidate_without_mutation():
    from app.rpg.locations import apply_seeded_encounter_runtime

    state = {"player_state": {"hp": 10}, "combat_state": {"active": False}}
    before = deepcopy(state)
    result = apply_seeded_encounter_runtime(state, _combat_candidate_encounter(), turn_index=13)

    assert result["ok"] is True
    assert result["reason"] == "combat_candidate_created"
    assert result["world_event_result"] is None
    assert result["classification"]["kind"] == "combat_candidate"
    candidate = result["combat_candidate"]
    assert candidate["combat_candidate"] is True
    assert candidate["encounter_id"] == "encounter:old_mill_route:bandit_patrol"
    assert candidate["location_id"] == "location:old_mill"
    assert candidate["requires_canonical_combat_start_api"] is True
    assert state == before


def test_ci_phase4_encounter_runtime_contract_forbids_invented_outcomes():
    from app.rpg.locations import apply_seeded_encounter_runtime, build_encounter_runtime_narration_contract

    result = apply_seeded_encounter_runtime({}, _combat_candidate_encounter(), turn_index=14)
    contract = build_encounter_runtime_narration_contract(result)

    assert contract["source"] == "deterministic_phase4_encounter_combat_events"
    assert "Encounter runtime result: combat_candidate_created" in contract["allowed_encounter_runtime_claims"]
    assert "Combat candidate: encounter:old_mill_route:bandit_patrol at location:old_mill" in contract[
        "allowed_encounter_runtime_claims"
    ]
    forbidden = "\n".join(contract["forbidden_encounter_runtime_claims"])
    assert "Do not claim combat started" in forbidden
    assert "Do not invent enemies" in forbidden
    assert "Do not mutate inventory" in forbidden
    assert "Do not invent local world events" in forbidden


def test_ci_phase4_encounter_combat_events_readiness_and_exports():
    from app.rpg import locations

    readiness = locations.assert_phase4_encounter_combat_events_ready()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase4_encounter_combat_events_ready"
    assert readiness["blockers"] == []
    assert readiness["source"] == "deterministic_phase4_encounter_combat_events"
    assert locations.apply_seeded_encounter_runtime
    assert locations.classify_encounter_resolution
    assert locations.build_encounter_runtime_narration_contract
