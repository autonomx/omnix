"""Regression tests for Phase 15.3 — Session lifecycle unification."""
from app.rpg.session.service import (
    create_or_normalize_session,
    export_session_as_package,
    import_session_from_package,
)


def test_regression_normalize_does_not_lose_extra_fields():
    """Normalization should not strip extra simulation_state fields."""
    session = {
        "manifest": {"id": "s1"},
        "simulation_state": {
            "custom_field": "preserved",
            "extra_data": [1, 2, 3],
        },
    }
    out = create_or_normalize_session(session)
    assert out["simulation_state"]["custom_field"] == "preserved"
    assert out["simulation_state"]["extra_data"] == [1, 2, 3]


def test_regression_import_rejects_none():
    """Importing None should return ok=False, not crash."""
    result = import_session_from_package(None)
    assert result["ok"] is False


def test_regression_export_handles_empty_manifest():
    """Exporting a session with no manifest should not crash."""
    session = {"simulation_state": {}}
    package = export_session_as_package(session)
    assert package["session_manifest"]["id"] == "session:unknown"


def test_regression_normalize_preserves_installed_packs():
    """Normalization should not clear existing installed_packs."""
    session = {
        "manifest": {"id": "s1"},
        "simulation_state": {},
        "installed_packs": ["core", "extra"],
    }
    out = create_or_normalize_session(session)
    assert "core" in out["installed_packs"]
    assert "extra" in out["installed_packs"]


def test_regression_service_round_trip_stable():
    """Multiple round trips through service should be stable."""
    session = {
        "manifest": {"id": "stable_test"},
        "simulation_state": {
            "memory_state": {
                "actor_memory": {"npc:a": {"entries": [{"text": "fact", "strength": 0.5}]}},
                "world_memory": {"rumors": []},
            }
        },
        "installed_packs": ["z", "a"],
    }

    for _ in range(3):
        package = export_session_as_package(session)
        result = import_session_from_package(package)
        assert result["ok"] is True
        session = result["session"]

    assert session["manifest"]["id"] == "stable_test"
