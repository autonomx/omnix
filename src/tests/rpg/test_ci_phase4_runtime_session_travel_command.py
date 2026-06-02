from copy import deepcopy


def _session_id(name: str) -> str:
    return f"ci_phase4_13_{name}"


def _base_session(session_id: str, *, items=None):
    return {
        "manifest": {"session_id": session_id, "id": session_id},
        "setup_payload": {},
        "runtime_state": {"tick": 3, "narration_mode": "deterministic"},
        "simulation_state": {
            "player_state": {
                "inventory_state": {"items": deepcopy(items if items is not None else [])},
                "survival_state": {"hunger": 10, "thirst": 10},
            },
            "travel_state": {"current_location_id": "location:rusty_flagon"},
        },
    }


def _ready_old_mill_session(session_id: str):
    from app.rpg.locations import OLD_MILL, discover_location, discover_route, unblock_route

    session = _base_session(
        session_id,
        items=[{"item_id": "ration", "qty": 1}, {"item_id": "water_skin", "qty": 2}],
    )
    state = session["simulation_state"]
    discover_location(state, location_id=OLD_MILL, reason="scouted_old_road", turn_index=1)
    discover_route(state, edge_id="route:old_road:old_mill", reason="scouted_old_road", turn_index=1)
    unblock_route(state, edge_id="route:old_road:old_mill", reason="bandit_threat_resolved", turn_index=2)
    return session


def _install_runtime_session(monkeypatch, runtime, session):
    saved = {}

    def load_runtime_session(session_id):
        if session_id == session["manifest"]["session_id"]:
            return deepcopy(session)
        return None

    def save_runtime_session(payload):
        saved.clear()
        saved.update(deepcopy(payload))
        return payload

    monkeypatch.setattr(runtime, "load_runtime_session", load_runtime_session)
    monkeypatch.setattr(runtime, "save_runtime_session", save_runtime_session)
    return saved


def test_ci_phase4_session_runtime_routes_successful_travel_through_guarded_command_helper(monkeypatch):
    from app.rpg.locations import OLD_MILL
    from app.rpg.session import runtime

    session_id = _session_id("success")
    saved = _install_runtime_session(monkeypatch, runtime, _ready_old_mill_session(session_id))

    result = runtime._apply_turn_authoritative(
        session_id=session_id,
        player_input="travel to the old mill",
        performance_override={"narration_mode": "deterministic"},
    )

    assert result["ok"] is True
    assert result["source"] == "deterministic_phase4_session_travel_command_integration"
    assert result["result"]["action_type"] == "travel"
    assert result["travel_command_result"]["reason"] == "runtime_travel_command_applied"
    assert result["travel_result"]["reason"] == "runtime_travel_resources_consumed"
    assert result["simulation_state"]["travel_state"]["current_location_id"] == OLD_MILL
    assert result["simulation_state"]["player_state"]["inventory_state"]["items"] == []
    assert result["encounter_result"]["reason"] == "encounter_recorded"
    assert result["runtime_travel_command_narration_contract"]["source"] == (
        "deterministic_phase4_runtime_travel_encounter_routing"
    )
    assert saved["simulation_state"]["travel_state"]["current_location_id"] == OLD_MILL
    assert saved["runtime_state"]["last_turn_result"]["source"] == (
        "deterministic_phase4_session_travel_command_integration"
    )


def test_ci_phase4_session_runtime_denies_missing_resources_before_travel_or_encounter(monkeypatch):
    from app.rpg.locations import RUSTY_FLAGON
    from app.rpg.session import runtime

    session_id = _session_id("missing_resources")
    original = _base_session(session_id, items=[])
    _install_runtime_session(monkeypatch, runtime, original)

    result = runtime._apply_turn_authoritative(
        session_id=session_id,
        player_input="go to old road",
        performance_override={"narration_mode": "deterministic"},
    )

    assert result["ok"] is True
    assert result["result"]["ok"] is False
    assert result["travel_command_result"]["reason"] == "insufficient_travel_resources"
    assert result["travel_result"]["travel_result"] is None
    assert result["encounter_result"] == {}
    assert result["encounter_runtime_result"] == {}
    assert result["simulation_state"]["travel_state"]["current_location_id"] == RUSTY_FLAGON
    assert result["simulation_state"]["player_state"] == original["simulation_state"]["player_state"]


def test_ci_phase4_session_runtime_leaves_non_travel_commands_on_existing_runtime_path(monkeypatch):
    from app.rpg.session import runtime

    session_id = _session_id("non_travel")
    _install_runtime_session(
        monkeypatch,
        runtime,
        _base_session(session_id, items=[{"item_id": "ration", "qty": 1}]),
    )

    delegated = {
        "ok": True,
        "source": "existing_authoritative_runtime_path",
        "travel_command_result": None,
    }
    monkeypatch.setattr(runtime, "_base_apply_turn_authoritative", lambda *args, **kwargs: delegated)

    result = runtime._apply_turn_authoritative(
        session_id=session_id,
        player_input="ask bran about work",
        performance_override={"narration_mode": "deterministic"},
    )

    assert result == delegated
