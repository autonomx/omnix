"""Unit tests for Phase 15.1 — Session/package bridge."""
from app.rpg.session.package_bridge import session_to_package, package_to_session


def test_session_to_package_basic():
    session = {
        "manifest": {"id": "s1", "title": "Campaign A"},
        "simulation_state": {},
        "installed_packs": [],
    }
    package_payload = session_to_package(session)
    assert package_payload["package_manifest"]["source_session_id"] == "s1"
    assert package_payload["session_manifest"] == session["manifest"]
    assert package_payload["installed_packs"] == []


def test_package_to_session_basic():
    package_payload = {
        "package_manifest": {"source_session_id": "s1"},
        "session_manifest": {"id": "s2"},
        "simulation_state": {},
        "installed_packs": [],
    }
    session = package_to_session(package_payload)
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
    assert package_payload["package_manifest"]["schema_version"] == 2


def test_package_to_session_defaults_schema_version():
    """Test that missing schema_version defaults to 2."""
    package_payload = {
        "package_manifest": {},
        "session_manifest": {"id": "s2"},
        "simulation_state": {},
        "installed_packs": ["pack:alpha"],
    }
    session = package_to_session(package_payload)
    assert session["manifest"]["schema_version"] == 2
    assert session["installed_packs"] == ["pack:alpha"]