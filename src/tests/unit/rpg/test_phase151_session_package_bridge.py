"""Unit tests for Phase 15.2 — Session/package bridge with validation and normalization."""
from app.rpg.session.package_bridge import package_to_session, session_to_package, validate_package_payload


def test_session_to_package_basic():
    session = {
        "manifest": {"id": "s1", "title": "Campaign A"},
        "simulation_state": {},
        "installed_packs": [],
    }
    package_payload = session_to_package(session)
    assert package_payload["package_manifest"]["source_session_id"] == "s1"
    assert package_payload["session_manifest"]["id"] == "s1"
    assert package_payload["installed_packs"] == []


def test_package_to_session_basic():
    package_payload = {
        "package_manifest": {"source_session_id": "s1", "schema_version": 1},
        "session_manifest": {"id": "s2"},
        "simulation_state": {},
        "installed_packs": [],
    }
    result = package_to_session(package_payload)
    assert result["ok"] is True
    session = result["session"]
    assert session["manifest"]["id"] == "s2"
    assert "import_metadata" in session


def test_session_to_package_preserves_schema_version():
    """Test that schema_version is preserved in package manifest."""
    session = {
        "manifest": {"id": "s1", "title": "Campaign A", "schema_version": 2},
        "simulation_state": {},
        "installed_packs": [],
    }
    package_payload = session_to_package(session)
    assert package_payload["package_manifest"]["schema_version"] == 1  # package schema version


def test_package_to_session_defaults_schema_version():
    """Test that missing schema_version on session manifest defaults to 2."""
    package_payload = {
        "package_manifest": {"schema_version": 1},
        "session_manifest": {"id": "s2"},
        "simulation_state": {},
        "installed_packs": ["pack:alpha"],
    }
    result = package_to_session(package_payload)
    assert result["ok"] is True
    session = result["session"]
    assert session["manifest"]["schema_version"] == 2
    assert session["installed_packs"] == ["pack:alpha"]


def test_session_package_round_trip_preserves_manifest_state_and_packs():
    session = {
        "manifest": {"id": "s1", "title": "Campaign A", "schema_version": 2},
        "simulation_state": {
            "presentation_state": {
                "visual_state": {
                    "image_requests": [{"request_id": "req:1", "kind": "character_portrait", "target_id": "npc:a"}],
                    "visual_assets": [{"asset_id": "asset:1", "kind": "character_portrait", "target_id": "npc:a"}],
                }
            },
            "memory_state": {
                "actor_memory": {"npc:a": {"entries": [{"text": "Known fact", "strength": 0.7}]}},
                "world_memory": {"rumors": [{"text": "Bridge rumor", "strength": 0.8, "reach": 2}]},
            },
        },
        "installed_packs": ["portraits", "core"],
    }

    package_payload = session_to_package(session)
    restored = package_to_session(package_payload)

    assert restored["ok"] is True
    restored_session = restored["session"]
    assert restored_session["manifest"]["id"] == "s1"
    assert restored_session["installed_packs"] == ["core", "portraits"]
    assert "presentation_state" in restored_session["simulation_state"]
    assert "memory_state" in restored_session["simulation_state"]


def test_validate_package_payload_rejects_missing_session_manifest():
    package_payload = {
        "package_manifest": {"schema_version": 1},
        "simulation_state": {},
        "installed_packs": [],
    }
    result = validate_package_payload(package_payload)
    assert result["ok"] is False
    assert "missing_session_manifest_id" in result["errors"]


def test_validate_package_payload_rejects_wrong_schema_version():
    package_payload = {
        "package_manifest": {"schema_version": 999},
        "session_manifest": {"id": "s1"},
        "simulation_state": {},
        "installed_packs": [],
    }
    result = validate_package_payload(package_payload)
    assert result["ok"] is False
    assert "unsupported_package_schema_version" in result["errors"]


def test_validate_package_payload_accepts_valid():
    package_payload = {
        "package_manifest": {"schema_version": 1},
        "session_manifest": {"id": "s1"},
        "simulation_state": {},
        "installed_packs": [],
    }
    result = validate_package_payload(package_payload)
    assert result["ok"] is True
    assert result["errors"] == []


def test_export_does_not_include_queue_runtime_state():
    session = {
        "manifest": {"id": "s1", "title": "Campaign A", "schema_version": 2},
        "simulation_state": {
            "presentation_state": {
                "visual_state": {
                    "image_requests": [{"request_id": "req:1"}],
                    "visual_assets": [{"asset_id": "asset:1"}],
                    "queue_jobs": [{"job_id": "job:1", "lease_token": "secret"}],
                }
            },
            "memory_state": {},
        },
        "installed_packs": [],
    }
    package_payload = session_to_package(session)
    visual_state = package_payload["simulation_state"]["presentation_state"]["visual_state"]
    assert "queue_jobs" not in visual_state


def test_export_sorts_installed_packs():
    session = {
        "manifest": {"id": "s1"},
        "simulation_state": {},
        "installed_packs": ["z_pack", "a_pack", "m_pack"],
    }
    package_payload = session_to_package(session)
    assert package_payload["installed_packs"] == ["a_pack", "m_pack", "z_pack"]


def test_export_normalizes_visual_assets_deterministically():
    session = {
        "manifest": {"id": "s1"},
        "simulation_state": {
            "presentation_state": {
                "visual_state": {
                    "image_requests": [],
                    "visual_assets": [
                        {"asset_id": "z:1", "kind": "portrait", "target_id": "a"},
                        {"asset_id": "a:1", "kind": "portrait", "target_id": "b"},
                    ],
                }
            },
            "memory_state": {},
        },
        "installed_packs": [],
    }
    package_payload = session_to_package(session)
    assets = package_payload["simulation_state"]["presentation_state"]["visual_state"]["visual_assets"]
    assert assets[0]["asset_id"] == "a:1"
    assert assets[1]["asset_id"] == "z:1"


def test_export_normalizes_memory_state():
    session = {
        "manifest": {"id": "s1"},
        "simulation_state": {
            "presentation_state": {"visual_state": {}},
            "memory_state": {
                "actor_memory": {
                    "npc:b": {"entries": [{"text": "fact B", "strength": 0.3}]},
                    "npc:a": {"entries": [{"text": "fact A", "strength": 0.9}]},
                },
                "world_memory": {"rumors": [{"text": "rumor1", "strength": 0.5, "reach": 1}]},
            },
        },
        "installed_packs": [],
    }
    package_payload = session_to_package(session)
    memory = package_payload["simulation_state"]["memory_state"]
    actor_ids = list(memory["actor_memory"].keys())
    assert actor_ids == ["npc:a", "npc:b"]


def test_package_to_session_rejects_invalid_payload():
    result = package_to_session({})
    assert result["ok"] is False
    assert len(result["errors"]) > 0


def test_session_to_package_handles_none_input():
    package_payload = session_to_package(None)
    assert package_payload["package_manifest"]["package_kind"] == "rpg_session_export"
    assert package_payload["session_manifest"]["id"] == "session:unknown"


def test_package_to_session_backward_compat_kwargs():
    """Verify session_id/title kwargs override manifest values."""
    package_payload = {
        "package_manifest": {"schema_version": 1},
        "session_manifest": {"id": "orig"},
        "simulation_state": {},
        "installed_packs": [],
    }
    result = package_to_session(package_payload, session_id="override_id", title="Override Title")
    assert result["ok"] is True
    assert result["session"]["manifest"]["id"] == "override_id"
    assert result["session"]["manifest"]["title"] == "Override Title"