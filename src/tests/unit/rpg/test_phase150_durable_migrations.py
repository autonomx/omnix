"""Unit tests for Phase 15.0 — Durable session migrations."""
from app.rpg.session.migrations import migrate_session_payload


def test_migrate_session_payload_preserves_current_version():
    payload = {"save_version": "1.0", "session": {"manifest": {"id": "s1", "schema_version": 2}}}
    result = migrate_session_payload(payload)
    assert result["save_version"] == "1.0"


def test_migrate_session_payload_handles_unversioned():
    payload = {"session": {}}
    result = migrate_session_payload(payload)
    # Result has manifest at top level, simulation_state has presentation_state and memory_state
    assert result["manifest"]["id"] == "session:unknown"
    assert "presentation_state" in result["simulation_state"]
    assert "memory_state" in result["simulation_state"]


def test_migrate_session_payload_sets_missing_manifest_id_and_roots():
    """Test that missing manifest id and root states are set."""
    payload = {"manifest": {}, "simulation_state": {}}
    out = migrate_session_payload(payload)
    assert out["manifest"]["id"] == "session:unknown"
    assert "presentation_state" in out["simulation_state"]
    assert "memory_state" in out["simulation_state"]