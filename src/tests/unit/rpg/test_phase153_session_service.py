"""Unit tests for Phase 15.3 — Canonical session service."""
from app.rpg.session.service import (
    create_or_normalize_session,
    export_session_as_package,
    import_session_from_package,
)


def test_create_or_normalize_session_adds_defaults():
    session = {"manifest": {"id": "s1"}, "simulation_state": {}}
    out = create_or_normalize_session(session)
    assert out["manifest"]["id"] == "s1"
    assert "installed_packs" in out
    assert "presentation_state" in out["simulation_state"]
    assert "memory_state" in out["simulation_state"]


def test_create_or_normalize_session_handles_none():
    out = create_or_normalize_session(None)
    assert "manifest" in out
    assert "installed_packs" in out


def test_create_or_normalize_session_preserves_existing_packs():
    session = {
        "manifest": {"id": "s1"},
        "simulation_state": {},
        "installed_packs": ["pack1", "pack2"],
    }
    out = create_or_normalize_session(session)
    assert out["installed_packs"] == ["pack1", "pack2"]


def test_export_session_as_package_uses_canonical_normalization():
    session = {"manifest": {"id": "s1"}, "simulation_state": {}}
    package_payload = export_session_as_package(session)
    assert package_payload["session_manifest"]["id"] == "s1"
    assert package_payload["package_manifest"]["package_kind"] == "rpg_session_export"


def test_export_session_ensures_migration_before_export():
    session = {"manifest": {"id": "s1", "schema_version": 1}, "simulation_state": {}}
    package_payload = export_session_as_package(session)
    # After migration, session manifest should have schema_version 2
    assert package_payload["session_manifest"]["schema_version"] == 2


def test_import_session_from_package_valid():
    package_payload = {
        "package_manifest": {"schema_version": 1},
        "session_manifest": {"id": "imported"},
        "simulation_state": {},
        "installed_packs": [],
    }
    result = import_session_from_package(package_payload)
    assert result["ok"] is True
    session = result["session"]
    assert session["manifest"]["id"] == "imported"
    assert "installed_packs" in session
    assert "presentation_state" in session["simulation_state"]
    assert "memory_state" in session["simulation_state"]


def test_import_session_from_package_rejects_invalid():
    result = import_session_from_package({})
    assert result["ok"] is False
    assert len(result["errors"]) > 0


def test_import_session_normalizes_after_conversion():
    """Import should run migration/normalization after package_to_session."""
    package_payload = {
        "package_manifest": {"schema_version": 1},
        "session_manifest": {"id": "s1"},
        "simulation_state": {"some_old_field": True},
        "installed_packs": ["core"],
    }
    result = import_session_from_package(package_payload)
    assert result["ok"] is True
    session = result["session"]
    # Migration should ensure sub-states exist
    assert "presentation_state" in session["simulation_state"]
    assert "memory_state" in session["simulation_state"]


def test_export_import_round_trip_through_service():
    """Full round-trip through service layer."""
    session = {
        "manifest": {"id": "s1", "title": "Test"},
        "simulation_state": {
            "memory_state": {
                "actor_memory": {"npc:a": {"entries": [{"text": "hello", "strength": 0.5}]}},
                "world_memory": {"rumors": []},
            }
        },
        "installed_packs": ["core"],
    }
    package = export_session_as_package(session)
    result = import_session_from_package(package)
    assert result["ok"] is True
    restored = result["session"]
    assert restored["manifest"]["id"] == "s1"
    mem = restored["simulation_state"]["memory_state"]
    assert "npc:a" in mem["actor_memory"]
