"""Unit tests for Phase 13.5 — Session lifecycle + persistence."""
from app.rpg.session.session_store import (
    archive_session,
    ensure_session_registry,
    get_session,
    list_sessions,
    save_session,
)


def test_save_and_list_session():
    root = {"sessions": []}
    root = save_session(root, {"manifest": {"id": "s1", "title": "Session 1"}, "state": {}})
    sessions = list_sessions(root)
    assert len(sessions) == 1


def test_get_session():
    root = {"sessions": [{"manifest": {"id": "s1", "title": "Session 1"}, "state": {}}]}
    session = get_session(root, "s1")
    assert session is not None


def test_archive_session():
    root = {"sessions": [{"manifest": {"id": "s1", "title": "Session 1"}, "state": {}}]}
    root = archive_session(root, "s1")
    assert root["sessions"][0]["manifest"]["status"] == "archived"


def test_save_session_upsert():
    root = {"sessions": []}
    root = save_session(root, {"manifest": {"id": "s1", "title": "Session 1"}, "state": {}})
    root = save_session(root, {"manifest": {"id": "s1", "title": "Updated Session"}, "state": {}})
    sessions = list_sessions(root)
    assert len(sessions) == 1
    assert sessions[0]["manifest"]["title"] == "Updated Session"


def test_get_session_not_found():
    root = {"sessions": []}
    session = get_session(root, "nonexistent")
    assert session is None


def test_ensure_session_registry_sorts():
    root = {"sessions": [
        {"manifest": {"id": "s2", "title": "Beta"}, "state": {}},
        {"manifest": {"id": "s1", "title": "Alpha"}, "state": {}},
    ]}
    root = ensure_session_registry(root)
    assert root["sessions"][0]["manifest"]["title"] == "Alpha"