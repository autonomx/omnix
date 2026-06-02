from copy import deepcopy
import inspect


def _session():
    return {
        "manifest": {"id": "phase7:test", "session_id": "phase7:test", "title": "Replay Test"},
        "installed_packs": ["base"],
        "simulation_state": {
            "player_state": {
                "inventory_state": {"items": [{"item_id": "ration", "qty": 1}]},
                "survival_state": {"hunger": 10, "thirst": 9},
            },
            "travel_state": {"current_location_id": "location:rusty_flagon"},
            "time_state": {
                "day_count": 1,
                "weather_id": "weather:clear_mild",
                "weather_label": "Clear and mild",
            },
        },
        "runtime_state": {"tick": 2, "elapsed_ms": 999, "last_player_action": {"action_type": "observe"}},
    }


def test_ci_phase7_checkpoint_digest_is_deterministic_and_filters_volatile_runtime_fields():
    from app.rpg.session import build_session_checkpoint

    first_session = _session()
    second_session = deepcopy(first_session)
    second_session["runtime_state"]["elapsed_ms"] = 1
    second_session["runtime_state"]["provider_latency_ms"] = 9999

    first = build_session_checkpoint(first_session, label="first", turn_index=2)
    second = build_session_checkpoint(second_session, label="second", turn_index=2)

    assert first["source"] == "deterministic_phase7_replay_checkpoint_foundation"
    assert first["schema_version"] == 1
    assert first["digest"] == second["digest"]
    assert "elapsed_ms" not in first["session"]["runtime_state"]
    assert "provider_latency_ms" not in second["session"]["runtime_state"]


def test_ci_phase7_checkpoint_restore_validates_digest():
    from app.rpg.session import build_session_checkpoint, restore_session_from_checkpoint

    checkpoint = build_session_checkpoint(_session(), label="restore", turn_index=2)
    restored = restore_session_from_checkpoint(checkpoint)
    tampered = deepcopy(checkpoint)
    tampered["session"]["simulation_state"]["travel_state"]["current_location_id"] = "location:old_road"
    rejected = restore_session_from_checkpoint(tampered)

    assert restored["ok"] is True
    assert restored["digest"] == checkpoint["digest"]
    assert rejected["ok"] is False
    assert rejected["reason"] == "checkpoint_digest_mismatch"
    assert rejected["source"] == "deterministic_phase7_replay_checkpoint_foundation"


def test_ci_phase7_checkpoint_compare_reports_drift_sections():
    from app.rpg.session import build_session_checkpoint, compare_session_checkpoints

    before = build_session_checkpoint(_session(), label="before", turn_index=2)
    changed_session = _session()
    changed_session["simulation_state"]["travel_state"]["current_location_id"] = "location:old_road"
    after = build_session_checkpoint(changed_session, label="after", turn_index=3)
    comparison = compare_session_checkpoints(before, after)

    assert comparison["ok"] is True
    assert comparison["deterministic_match"] is False
    assert comparison["before_digest"] != comparison["after_digest"]
    assert comparison["changed_sections"] == ["simulation_state"]


def test_ci_phase7_checkpoint_contract_forbids_provider_and_mutation():
    from app.rpg.session import build_replay_checkpoint_contract, build_session_checkpoint
    from app.rpg.session import replay_checkpoint

    checkpoint = build_session_checkpoint(_session(), label="contract", turn_index=2)
    contract = build_replay_checkpoint_contract(checkpoint)
    source = inspect.getsource(replay_checkpoint).lower()

    assert "Checkpoint digest: " + checkpoint["digest"] in contract["allowed_checkpoint_claims"]
    assert "Do not call providers or LLMs to build, restore, or compare replay checkpoints." in contract[
        "forbidden_checkpoint_claims"
    ]
    assert "openai" not in source
    assert "requests." not in source
    assert "httpx" not in source
    assert "urllib" not in source
    assert "subprocess" not in source


def test_ci_phase7_checkpoint_roundtrip_is_non_mutating():
    from app.rpg.session import build_session_checkpoint, restore_session_from_checkpoint

    session = _session()
    before = deepcopy(session)
    checkpoint = build_session_checkpoint(session, label="non_mutating", turn_index=2)
    restored = restore_session_from_checkpoint(checkpoint)

    assert session == before
    assert restored["ok"] is True
    assert restored["session"] == checkpoint["session"]
    assert restored["session"] is not session


def test_ci_phase7_checkpoint_readiness_and_exports():
    from app.rpg import session

    readiness = session.assert_phase7_replay_checkpoint_foundation_ready()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase7_replay_checkpoint_foundation_ready"
    assert readiness["blockers"] == []
    assert readiness["source"] == "deterministic_phase7_replay_checkpoint_foundation"
    assert session.build_session_checkpoint
    assert session.restore_session_from_checkpoint
    assert session.compare_session_checkpoints
    assert session.session_checkpoint_digest
