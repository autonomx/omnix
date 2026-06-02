from copy import deepcopy
import inspect


def _seed_session():
    from app.rpg.locations.discovery import discover_location, discover_route, unblock_route

    session = {
        "manifest": {"id": "phase7:roundtrip", "session_id": "phase7:roundtrip", "title": "Phase 7.3 Roundtrip"},
        "installed_packs": ["base"],
        "simulation_state": {
            "player_state": {
                "inventory_state": {"items": [{"item_id": "ration", "qty": 2}, {"item_id": "water_skin", "qty": 3}]},
                "survival_state": {"hunger": 10, "thirst": 10},
                "currency": {"silver": 5},
            },
            "quest_state": {"active_quests": [{"quest_id": "quest:old_mill", "status": "active"}]},
        },
        "runtime_state": {"elapsed_ms": 999, "provider_latency_ms": 100},
    }
    state = session["simulation_state"]
    discover_location(state, location_id="location:old_mill", reason="phase7_roundtrip_seed", turn_index=0)
    discover_route(state, edge_id="route:old_road:old_mill", reason="phase7_roundtrip_seed", turn_index=0)
    unblock_route(state, edge_id="route:old_road:old_mill", reason="phase7_roundtrip_seed", turn_index=0)
    return session


def _commands():
    return [
        {"type": "travel", "command_text": "go to the old road", "roll_encounter": False},
        {"type": "travel", "command_text": "go to the old mill", "roll_encounter": False},
    ]


def _memory_store():
    store = {}

    def save_session(session):
        stored = deepcopy(session)
        store[stored["manifest"]["session_id"]] = stored
        return stored

    def load_session(session_id):
        return deepcopy(store.get(session_id))

    return save_session, load_session


def test_ci_phase7_save_load_replay_roundtrip_validates_memory_store_digest_match():
    from app.rpg.session import run_save_load_replay_persistence_roundtrip

    save_session, load_session = _memory_store()
    result = run_save_load_replay_persistence_roundtrip(
        _seed_session(),
        _commands(),
        save_session=save_session,
        load_session=load_session,
        label="ci",
    )

    assert result["source"] == "deterministic_phase7_save_load_replay_roundtrip_gate"
    assert result["ok"] is True
    assert result["reason"] == "save_load_replay_persistence_roundtrip_validated"
    assert result["package_comparison"]["deterministic_match"] is True
    assert result["disk_comparison"]["deterministic_match"] is True
    assert result["replay_validation"]["ok"] is True
    assert result["expected_validation"]["ok"] is True
    assert result["blockers"] == []


def test_ci_phase7_save_load_replay_roundtrip_uses_existing_package_and_replay_paths():
    from app.rpg.session import run_save_load_replay_persistence_roundtrip

    save_session, load_session = _memory_store()
    result = run_save_load_replay_persistence_roundtrip(
        _seed_session(),
        _commands(),
        save_session=save_session,
        load_session=load_session,
        label="ci",
    )
    final_state = result["replay_validation"]["first"]["final_checkpoint"]["session"]["simulation_state"]
    player_state = final_state["player_state"]

    assert result["package_comparison"]["changed_sections"] == []
    assert result["disk_comparison"]["changed_sections"] == []
    assert final_state["travel_state"]["current_location_id"] == "location:old_mill"
    assert player_state["inventory_state"]["items"]
    assert isinstance(player_state.get("survival_state"), dict)
    assert isinstance(player_state.get("currency"), dict)
    assert final_state["quest_state"]["active_quests"][0]["quest_id"] == "quest:old_mill"


def test_ci_phase7_save_load_replay_roundtrip_detects_disk_drift():
    from app.rpg.session import run_save_load_replay_persistence_roundtrip

    saved = {}

    def save_session(session):
        saved[session["manifest"]["session_id"]] = deepcopy(session)
        return deepcopy(session)

    def load_session(session_id):
        loaded = deepcopy(saved[session_id])
        loaded["simulation_state"]["player_state"]["currency"]["silver"] = 4
        return loaded

    result = run_save_load_replay_persistence_roundtrip(
        _seed_session(),
        _commands(),
        save_session=save_session,
        load_session=load_session,
        label="ci",
    )

    blocker_kinds = {row["kind"] for row in result["blockers"]}

    assert result["ok"] is False
    assert result["reason"] == "save_load_replay_persistence_roundtrip_drift_detected"
    assert result["disk_comparison"]["deterministic_match"] is False
    assert result["disk_comparison"]["changed_sections"] == ["simulation_state"]
    assert "disk_roundtrip_digest_drift" in blocker_kinds


def test_ci_phase7_save_load_replay_roundtrip_contract_and_exports():
    from app.rpg import session
    from app.rpg.session import replay_persistence_roundtrip_v2

    readiness = session.assert_phase7_save_load_replay_roundtrip_ready()
    contract = session.build_save_load_replay_roundtrip_contract(readiness["result"])
    source = inspect.getsource(replay_persistence_roundtrip_v2).lower()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase7_save_load_replay_roundtrip_ready"
    assert readiness["blockers"] == []
    assert contract["source"] == "deterministic_phase7_save_load_replay_roundtrip_gate"
    assert "Roundtrip result: save_load_replay_persistence_roundtrip_validated" in contract["allowed_roundtrip_claims"]
    assert session.run_save_load_replay_persistence_roundtrip
    assert session.build_save_load_replay_roundtrip_contract
    assert session.assert_phase7_save_load_replay_roundtrip_ready
    assert "openai" not in source
    assert "requests." not in source
    assert "httpx" not in source
    assert "subprocess" not in source
