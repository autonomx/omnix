"""Functional tests for Phase 15.3 — Session lifecycle unification."""
from app.rpg.session.service import (
    create_or_normalize_session,
    export_session_as_package,
    import_session_from_package,
)


def test_service_normalizes_minimal_session():
    """Service should normalize a minimal session with all required fields."""
    session = {}
    out = create_or_normalize_session(session)
    assert "manifest" in out
    assert "simulation_state" in out
    assert "installed_packs" in out
    assert "presentation_state" in out["simulation_state"]
    assert "memory_state" in out["simulation_state"]


def test_service_export_import_preserves_full_state():
    """Full lifecycle: create → normalize → export → import → verify."""
    session = create_or_normalize_session({
        "manifest": {"id": "lifecycle_test", "title": "Lifecycle Test"},
        "simulation_state": {
            "presentation_state": {
                "visual_state": {
                    "image_requests": [{"request_id": "r1", "kind": "portrait", "target_id": "npc:a"}],
                    "visual_assets": [],
                }
            },
            "memory_state": {
                "actor_memory": {
                    "npc:a": {"entries": [{"text": "Important fact", "strength": 0.9}]}
                },
                "world_memory": {"rumors": [{"text": "Rumor A", "strength": 0.7, "reach": 3}]},
            },
        },
        "installed_packs": ["pack_b", "pack_a"],
    })

    # Export
    package = export_session_as_package(session)
    assert package["package_manifest"]["package_kind"] == "rpg_session_export"

    # Import
    result = import_session_from_package(package)
    assert result["ok"] is True
    restored = result["session"]

    # Verify all state preserved
    assert restored["manifest"]["id"] == "lifecycle_test"
    assert "pack_a" in restored["installed_packs"]
    mem = restored["simulation_state"]["memory_state"]
    assert "npc:a" in mem["actor_memory"]
    assert len(mem["world_memory"]["rumors"]) == 1


def test_service_handles_corrupted_package():
    """Service should gracefully reject corrupted package data."""
    corrupted_packages = [
        None,
        {},
        {"package_manifest": "not_dict"},
        {"package_manifest": {"schema_version": 999}},
    ]
    for pkg in corrupted_packages:
        result = import_session_from_package(pkg)
        assert result["ok"] is False


def test_service_idempotent_normalization():
    """Normalizing a session multiple times should be idempotent."""
    session = {"manifest": {"id": "s1"}, "simulation_state": {}}
    out1 = create_or_normalize_session(session)
    out2 = create_or_normalize_session(out1)
    assert out1["manifest"] == out2["manifest"]
    assert out1["installed_packs"] == out2["installed_packs"]
