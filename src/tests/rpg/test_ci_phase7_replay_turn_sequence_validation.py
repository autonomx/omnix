from copy import deepcopy
import inspect


def _seed_session():
    from app.rpg.locations.discovery import discover_location, discover_route, unblock_route

    session = {
        "manifest": {"id": "phase7:sequence", "session_id": "phase7:sequence"},
        "installed_packs": ["base"],
        "simulation_state": {
            "player_state": {
                "inventory_state": {"items": [{"item_id": "ration", "qty": 2}, {"item_id": "water_skin", "qty": 3}]},
                "survival_state": {"hunger": 10, "thirst": 10},
            }
        },
        "runtime_state": {"tick": 0, "elapsed_ms": 999},
    }
    state = session["simulation_state"]
    discover_location(state, location_id="location:old_mill", reason="phase7_replay_seed", turn_index=0)
    discover_route(state, edge_id="route:old_road:old_mill", reason="phase7_replay_seed", turn_index=0)
    unblock_route(state, edge_id="route:old_road:old_mill", reason="phase7_replay_seed", turn_index=0)
    return session


def _commands():
    return [
        {"type": "travel", "command_text": "go to the old road", "roll_encounter": False},
        {"type": "travel", "command_text": "go to the old mill", "roll_encounter": False},
        {"type": "travel", "command_text": "sing a song", "roll_encounter": False},
    ]


def test_ci_phase7_replay_sequence_runs_same_digest_twice():
    from app.rpg.session import build_session_checkpoint, validate_replay_turn_sequence

    session = _seed_session()
    checkpoint = build_session_checkpoint(session, label="start", turn_index=0)
    validation = validate_replay_turn_sequence(checkpoint, _commands(), label="ci")

    assert validation["source"] == "deterministic_phase7_replay_turn_sequence_validation"
    assert validation["ok"] is True
    assert validation["deterministic_match"] is True
    assert validation["comparison"]["before_digest"] == validation["comparison"]["after_digest"]
    assert validation["first"]["checkpoint_digests"] == validation["second"]["checkpoint_digests"]


def test_ci_phase7_replay_sequence_uses_canonical_runtime_command_helpers():
    from app.rpg.session import build_session_checkpoint, run_replay_turn_sequence

    session = _seed_session()
    checkpoint = build_session_checkpoint(session, label="start", turn_index=0)
    result = run_replay_turn_sequence(checkpoint, _commands(), label="ci")
    command_results = result["command_results"]
    final_state = result["final_checkpoint"]["session"]["simulation_state"]

    assert result["ok"] is True
    assert [row["reason"] for row in command_results] == [
        "runtime_travel_command_applied",
        "runtime_travel_command_applied",
        "not_travel_command",
    ]
    assert all(row["result_source"] for row in command_results)
    assert final_state["travel_state"]["current_location_id"] == "location:old_mill"
    assert final_state["player_state"]["inventory_state"]["items"]


def test_ci_phase7_replay_rejected_command_does_not_mutate_hidden_state():
    from app.rpg.session import build_session_checkpoint, run_replay_turn_sequence

    session = _seed_session()
    checkpoint = build_session_checkpoint(session, label="start", turn_index=0)
    before = run_replay_turn_sequence(checkpoint, _commands()[:2], label="before_reject")
    after = run_replay_turn_sequence(checkpoint, _commands(), label="after_reject")

    assert after["command_results"][-1]["reason"] == "not_travel_command"
    assert after["final_checkpoint"]["digest"] == before["final_checkpoint"]["digest"]


def test_ci_phase7_replay_sequence_detects_expected_checkpoint_drift():
    from app.rpg.session import build_session_checkpoint, validate_replay_turn_sequence

    session = _seed_session()
    checkpoint = build_session_checkpoint(session, label="start", turn_index=0)
    expected = build_session_checkpoint(deepcopy(session), label="wrong", turn_index=0)
    validation = validate_replay_turn_sequence(checkpoint, _commands(), expected_final_checkpoint=expected, label="ci")

    assert validation["ok"] is False
    assert validation["reason"] == "replay_turn_sequence_drift_detected"
    assert validation["deterministic_match"] is True
    assert validation["expected_match"] is False
    assert validation["expected_comparison"]["changed_sections"] == ["simulation_state"]


def test_ci_phase7_replay_sequence_contract_forbids_provider_and_shortcuts():
    from app.rpg.session import build_replay_turn_sequence_contract, build_session_checkpoint, validate_replay_turn_sequence
    from app.rpg.session import replay_turn_sequence

    checkpoint = build_session_checkpoint(_seed_session(), label="start", turn_index=0)
    validation = validate_replay_turn_sequence(checkpoint, _commands(), label="ci")
    contract = build_replay_turn_sequence_contract(validation)
    source = inspect.getsource(replay_turn_sequence).lower()

    assert "Replay result: replay_turn_sequence_validated" in contract["allowed_replay_claims"]
    assert "Do not call providers or LLMs while replaying deterministic turn sequences." in contract["forbidden_replay_claims"]
    assert "Do not bypass canonical runtime command helpers for replayed gameplay commands." in contract[
        "forbidden_replay_claims"
    ]
    assert "openai" not in source
    assert "requests." not in source
    assert "httpx" not in source
    assert "subprocess" not in source


def test_ci_phase7_replay_sequence_readiness_and_exports():
    from app.rpg import session

    readiness = session.assert_phase7_replay_turn_sequence_ready()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase7_replay_turn_sequence_ready"
    assert readiness["blockers"] == []
    assert readiness["source"] == "deterministic_phase7_replay_turn_sequence_validation"
    assert session.run_replay_turn_sequence
    assert session.validate_replay_turn_sequence
    assert session.build_replay_turn_sequence_contract
    assert session.default_replay_command_handlers
