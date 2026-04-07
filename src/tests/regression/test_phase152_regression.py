"""Regression tests for Phase 15.2 — Session/package round-trip hardening."""
from app.rpg.session.package_bridge import (
    package_to_session,
    session_to_package,
    validate_package_payload,
)


def test_regression_none_inputs_do_not_crash():
    """Previous versions could crash on None/missing fields."""
    pkg = session_to_package(None)
    assert pkg["package_manifest"]["package_kind"] == "rpg_session_export"

    result = package_to_session(None)
    assert result["ok"] is False


def test_regression_non_dict_fields_handled():
    """Non-dict fields in session should be safely handled."""
    session = {
        "manifest": "not_a_dict",
        "simulation_state": 42,
        "installed_packs": "not_a_list",
    }
    pkg = session_to_package(session)
    assert pkg["session_manifest"]["id"] == "session:unknown"
    assert pkg["installed_packs"] == []


def test_regression_package_import_rejects_schema_v0():
    """Schema version 0 should be rejected, not silently accepted."""
    pkg = {
        "package_manifest": {"schema_version": 0},
        "session_manifest": {"id": "s1"},
        "simulation_state": {},
        "installed_packs": [],
    }
    result = validate_package_payload(pkg)
    assert result["ok"] is False
    assert "unsupported_package_schema_version" in result["errors"]


def test_regression_visual_queue_excluded_from_export():
    """Queue/job runtime state must never leak into exported packages."""
    session = {
        "manifest": {"id": "s1"},
        "simulation_state": {
            "presentation_state": {
                "visual_state": {
                    "image_requests": [],
                    "visual_assets": [],
                    "queue_jobs": [{"job_id": "j1", "lease_token": "tok"}],
                    "active_worker": {"pid": 12345},
                }
            },
            "memory_state": {},
        },
        "installed_packs": [],
    }
    pkg = session_to_package(session)
    vs = pkg["simulation_state"]["presentation_state"]["visual_state"]
    assert "queue_jobs" not in vs
    assert "active_worker" not in vs


def test_regression_backward_compat_kwargs():
    """package_to_session must still accept session_id/title kwargs."""
    pkg = {
        "package_manifest": {"schema_version": 1},
        "session_manifest": {"id": "orig"},
        "simulation_state": {},
        "installed_packs": [],
    }
    result = package_to_session(pkg, session_id="new_id", title="New Title")
    assert result["ok"] is True
    assert result["session"]["manifest"]["id"] == "new_id"
    assert result["session"]["manifest"]["title"] == "New Title"


def test_regression_memory_capped_at_50_entries():
    """Actor memory entries should be capped to 50 per actor in export."""
    entries = [{"text": f"fact_{i}", "strength": float(i) / 100.0} for i in range(80)]
    session = {
        "manifest": {"id": "s1"},
        "simulation_state": {
            "presentation_state": {"visual_state": {}},
            "memory_state": {
                "actor_memory": {"npc:a": {"entries": entries}},
                "world_memory": {"rumors": []},
            },
        },
        "installed_packs": [],
    }
    pkg = session_to_package(session)
    exported_entries = pkg["simulation_state"]["memory_state"]["actor_memory"]["npc:a"]["entries"]
    assert len(exported_entries) == 50


def test_regression_visual_assets_capped():
    """Visual assets should be capped to 200 in export."""
    assets = [{"asset_id": f"a:{i}", "kind": "portrait", "target_id": f"npc:{i}"} for i in range(250)]
    session = {
        "manifest": {"id": "s1"},
        "simulation_state": {
            "presentation_state": {
                "visual_state": {
                    "image_requests": [],
                    "visual_assets": assets,
                }
            },
            "memory_state": {},
        },
        "installed_packs": [],
    }
    pkg = session_to_package(session)
    exported_assets = pkg["simulation_state"]["presentation_state"]["visual_state"]["visual_assets"]
    assert len(exported_assets) == 200


def test_regression_image_requests_capped():
    """Image requests should be capped to 100 in export."""
    reqs = [{"request_id": f"r:{i}", "kind": "portrait", "target_id": f"npc:{i}"} for i in range(150)]
    session = {
        "manifest": {"id": "s1"},
        "simulation_state": {
            "presentation_state": {
                "visual_state": {
                    "image_requests": reqs,
                    "visual_assets": [],
                }
            },
            "memory_state": {},
        },
        "installed_packs": [],
    }
    pkg = session_to_package(session)
    exported_reqs = pkg["simulation_state"]["presentation_state"]["visual_state"]["image_requests"]
    assert len(exported_reqs) == 100
