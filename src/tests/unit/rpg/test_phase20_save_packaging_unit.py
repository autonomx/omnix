"""Unit tests for Phase 20 save packaging fixes."""
from app.rpg.persistence.save_packaging import (
    SaveSnapshot,
    SaveBuilder,
    SaveSerializer,
    SavePackagingValidator,
    ReplayConsistencyChecker,
    SaveMigrator,
    SavePackagingState,
    MigrationRecord,
)


def test_phase20_save_builder_creates_integrity_hash():
    snapshot = SaveBuilder.build_snapshot(
        save_id="test:1",
        tick=10,
        simulation_state={"a": 1},
        metadata={"b": 2},
    )
    assert snapshot.integrity_hash != ""
    assert len(snapshot.integrity_hash) == 40  # SHA-1 hex length


def test_phase20_same_data_different_key_order_same_hash():
    snapshot_a = SaveBuilder.build_snapshot(
        save_id="test:2",
        tick=5,
        simulation_state={"b": 2, "a": 1},
    )
    snapshot_b = SaveBuilder.build_snapshot(
        save_id="test:2",
        tick=5,
        simulation_state={"a": 1, "b": 2},
    )
    assert snapshot_a.integrity_hash == snapshot_b.integrity_hash


def test_phase20_round_trip_preserves_data():
    snapshot = SaveBuilder.build_snapshot(
        save_id="test:3",
        tick=1,
        simulation_state={"x": 1, "y": {"z": 2}},
    )
    dumped = SaveSerializer.dump_snapshot(snapshot)
    loaded = SaveSerializer.load_snapshot(dumped)
    assert dumped == SaveSerializer.dump_snapshot(loaded)


def test_phase20_validation_catches_hash_mismatch():
    snapshot = SaveBuilder.build_snapshot(save_id="test:4", tick=1, simulation_state={})
    snapshot.integrity_hash = "invalid_hash"
    errors = SavePackagingValidator.validate_snapshot(snapshot)
    assert "integrity_hash mismatch" in errors


def test_phase20_normalize_snapshot_recomputes_hash():
    snapshot = SaveSnapshot(
        save_id="test:5",
        tick=-5,
        simulation_state={"c": 3, "a": 1, "b": 2},
    )
    normalized = SavePackagingValidator.normalize_snapshot(snapshot)
    assert normalized.tick == 0
    assert normalized.version >= 1
    expected_hash = SaveBuilder.compute_integrity_hash(normalized)
    assert normalized.integrity_hash == expected_hash


def test_phase20_migration_history_is_limited():
    state = SavePackagingState()
    for i in range(25):
        state.migration_history.append(
            MigrationRecord(from_version=i, to_version=i + 1, applied=True)
        )
    assert len(state.migration_history) == 25
    normalized = SavePackagingValidator.normalize_packaging_state(state)
    assert len(normalized.migration_history) == 20