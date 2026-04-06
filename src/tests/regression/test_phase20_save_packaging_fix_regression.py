"""Regression tests for Phase 20 save packaging fixes."""
from app.rpg.persistence.save_packaging import (
    SaveBuilder,
    SaveSerializer,
    SavePackagingValidator,
    ReplayConsistencyChecker,
)


def test_phase20_save_builder_produces_stable_integrity_hash():
    snapshot_a = SaveBuilder.build_snapshot(
        save_id="save:1",
        tick=5,
        simulation_state={"b": 2, "a": 1},
        metadata={"z": 9, "y": 8},
    )
    snapshot_b = SaveBuilder.build_snapshot(
        save_id="save:1",
        tick=5,
        simulation_state={"a": 1, "b": 2},
        metadata={"y": 8, "z": 9},
    )
    assert snapshot_a.integrity_hash == snapshot_b.integrity_hash
    assert snapshot_a.to_dict() == snapshot_b.to_dict()


def test_phase20_round_trip_is_deterministic():
    snapshot = SaveBuilder.build_snapshot(
        save_id="save:2",
        tick=10,
        simulation_state={
            "runtime_state": {"dialogue": {"turn_cursor": 2}},
            "orchestration_state": {"llm": {"provider_mode": "disabled"}},
        },
        metadata={"slot": "A"},
    )
    result = ReplayConsistencyChecker.check_round_trip(snapshot)
    assert result["matches"] is True


def test_phase20_load_snapshot_normalizes_and_recomputes_hash():
    snapshot = SaveBuilder.build_snapshot(
        save_id="save:3",
        tick=1,
        simulation_state={"x": 1},
        metadata={},
    )
    dumped = SaveSerializer.dump_snapshot(snapshot)
    loaded = SaveSerializer.load_snapshot(dumped)
    assert loaded.to_dict() == snapshot.to_dict()


def test_phase20_validator_flags_integrity_hash_mismatch():
    snapshot = SaveBuilder.build_snapshot(
        save_id="save:4",
        tick=3,
        simulation_state={"x": 1},
        metadata={},
    )
    snapshot.integrity_hash = "broken"
    errors = SavePackagingValidator.validate_snapshot(snapshot)
    assert "integrity_hash mismatch" in errors