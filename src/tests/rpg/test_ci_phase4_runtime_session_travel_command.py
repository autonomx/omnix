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


def _install_save_capture(monkeypatch, runtime_part27):
    saved = {}

    def save_runtime_session(payload):
        saved.clear()
        saved.update(deepcopy(payload))
        return payload

    monkeypatch.setattr(runtime_part27, "save_runtime_session", save_runtime_session)
    return saved


def test_ci_phase4_session_runtime_routes_successful_travel_through_guarded_command_helper(monkeypatch):
    from app.rpg.locations import OLD_MILL
    from app.rpg.session import runtime, runtime_part27

    assert runtime._apply_turn_authoritative.__module__ == "app.rpg.session.runtime_part27"
    session_id = _session_id("success")
    session = _ready_old_mill_session(session_id)
    saved = _install_save_capture(monkeypatch, runtime_part27)

    result = runtime_part27._apply_phase4_session_travel_command(
        session_id,
        "travel to the old mill",
        session=session,
        simulation_state=session["simulation_state"],
        runtime_state=session["runtime_state"],
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
    from app.rpg.session import runtime_part27

    session_id = _session_id("missing_resources")
    original = _base_session(session_id, items=[])
    session = deepcopy(original)
    _install_save_capture(monkeypatch, runtime_part27)

    result = runtime_part27._apply_phase4_session_travel_command(
        session_id,
        "go to old road",
        session=session,
        simulation_state=session["simulation_state"],
        runtime_state=session["runtime_state"],
    )

    assert result["ok"] is True
    assert result["result"]["ok"] is False
    assert result["travel_command_result"]["reason"] == "insufficient_travel_resources"
    assert result["travel_result"].get("travel_result") is None
    assert result["encounter_result"] == {}
    assert result["encounter_runtime_result"] == {}
    assert result["simulation_state"]["travel_state"]["current_location_id"] == RUSTY_FLAGON
    assert result["simulation_state"]["player_state"] == original["simulation_state"]["player_state"]


def test_ci_phase4_session_runtime_leaves_non_travel_commands_unclaimed():
    from app.rpg.session import runtime_part27

    session_id = _session_id("non_travel")
    session = _base_session(session_id, items=[{"item_id": "ration", "qty": 1}])

    result = runtime_part27._apply_phase4_session_travel_command(
        session_id,
        "ask bran about work",
        session=session,
        simulation_state=session["simulation_state"],
        runtime_state=session["runtime_state"],
    )

    assert result == {}
