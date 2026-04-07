"""Functional tests for Phase 15.2 — Session/package round-trip hardening."""
from app.rpg.session.package_bridge import (
    package_to_session,
    session_to_package,
    validate_package_payload,
)


def _build_rich_session():
    return {
        "manifest": {"id": "s1", "title": "Rich Campaign", "schema_version": 2},
        "simulation_state": {
            "presentation_state": {
                "visual_state": {
                    "image_requests": [
                        {"request_id": f"req:{i}", "kind": "portrait", "target_id": f"npc:{i}"}
                        for i in range(5)
                    ],
                    "visual_assets": [
                        {"asset_id": f"asset:{i}", "kind": "portrait", "target_id": f"npc:{i}"}
                        for i in range(5)
                    ],
                    "queue_jobs": [{"job_id": "j:1", "lease_token": "secret"}],
                }
            },
            "memory_state": {
                "actor_memory": {
                    "npc:warrior": {
                        "entries": [
                            {"text": "Fought dragon", "strength": 0.9},
                            {"text": "Met at tavern", "strength": 0.4},
                        ]
                    },
                    "npc:mage": {
                        "entries": [
                            {"text": "Taught fire spell", "strength": 0.7},
                        ]
                    },
                },
                "world_memory": {
                    "rumors": [
                        {"text": "King is ill", "strength": 0.8, "reach": 5},
                        {"text": "Dragon seen", "strength": 0.6, "reach": 3},
                    ]
                },
            },
        },
        "installed_packs": ["fantasy_core", "portraits", "advanced_magic"],
    }


def test_full_export_import_round_trip_preserves_all_data():
    """Full functional round-trip: export → validate → import preserves all data."""
    session = _build_rich_session()
    package = session_to_package(session)

    # Validate the package
    validation = validate_package_payload(package)
    assert validation["ok"] is True

    # Import back
    result = package_to_session(package)
    assert result["ok"] is True
    restored = result["session"]

    # Manifest preserved
    assert restored["manifest"]["id"] == "s1"
    assert restored["manifest"]["title"] == "Rich Campaign"

    # Packs sorted
    assert restored["installed_packs"] == ["advanced_magic", "fantasy_core", "portraits"]

    # Memory preserved
    mem = restored["simulation_state"]["memory_state"]
    assert "npc:warrior" in mem["actor_memory"]
    assert "npc:mage" in mem["actor_memory"]
    assert len(mem["world_memory"]["rumors"]) == 2

    # Visual preserved
    vis = restored["simulation_state"]["presentation_state"]["visual_state"]
    assert len(vis["image_requests"]) == 5
    assert len(vis["visual_assets"]) == 5

    # Queue state excluded
    assert "queue_jobs" not in vis


def test_export_import_multiple_cycles_is_idempotent():
    """Exporting and importing multiple times should be idempotent."""
    session = _build_rich_session()

    for _ in range(3):
        package = session_to_package(session)
        result = package_to_session(package)
        assert result["ok"] is True
        session = result["session"]

    assert session["manifest"]["id"] == "s1"
    assert session["installed_packs"] == ["advanced_magic", "fantasy_core", "portraits"]


def test_validation_blocks_invalid_import():
    """Invalid packages are rejected before import can corrupt state."""
    bad_packages = [
        {},  # empty
        {"package_manifest": {"schema_version": 999}},  # wrong version
        {"package_manifest": {"schema_version": 1}, "session_manifest": {}},  # missing id
    ]
    for pkg in bad_packages:
        result = package_to_session(pkg)
        assert result["ok"] is False
        assert len(result.get("errors", [])) > 0


def test_export_handles_edge_case_empty_session():
    """Exporting a minimal session produces valid package."""
    session = {"manifest": {"id": "empty"}, "simulation_state": {}, "installed_packs": []}
    package = session_to_package(session)
    assert package["package_manifest"]["package_kind"] == "rpg_session_export"
    validation = validate_package_payload(package)
    assert validation["ok"] is True


def test_memory_ordering_is_deterministic():
    """Memory entries are sorted deterministically across export cycles."""
    session = {
        "manifest": {"id": "s1"},
        "simulation_state": {
            "presentation_state": {"visual_state": {}},
            "memory_state": {
                "actor_memory": {
                    "npc:a": {
                        "entries": [
                            {"text": "Z fact", "strength": 0.5},
                            {"text": "A fact", "strength": 0.5},
                            {"text": "M fact", "strength": 0.8},
                        ]
                    }
                },
                "world_memory": {"rumors": []},
            },
        },
        "installed_packs": [],
    }
    pkg1 = session_to_package(session)
    pkg2 = session_to_package(session)

    entries1 = pkg1["simulation_state"]["memory_state"]["actor_memory"]["npc:a"]["entries"]
    entries2 = pkg2["simulation_state"]["memory_state"]["actor_memory"]["npc:a"]["entries"]
    assert entries1 == entries2
    # Highest strength first
    assert entries1[0]["text"] == "M fact"
