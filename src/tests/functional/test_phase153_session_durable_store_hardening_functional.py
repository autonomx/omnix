from pathlib import Path

import pytest

from app.rpg.session import durable_store


def _build_session(session_id: str = "session:test") -> dict:
    return {
        "manifest": {
            "id": session_id,
            "session_id": session_id,
            "title": "Durable Store Test",
            "schema_version": 2,
        },
        "simulation_state": {
            "tick": 12,
        },
        "runtime_state": {
            "tick": 12,
        },
        "installed_packs": [],
    }


def test_save_session_to_disk_is_atomic_and_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(durable_store, "_SESSION_DIR", Path(tmp_path))

    session = _build_session("session_atomic")
    saved = durable_store.save_session_to_disk(session)
    loaded = durable_store.load_session_from_disk("session_atomic")

    assert saved["manifest"]["id"] == "session_atomic"
    assert loaded is not None
    assert loaded["manifest"]["id"] == "session_atomic"
    assert loaded["simulation_state"]["tick"] == 12
    assert loaded["runtime_state"]["tick"] == 12


def test_load_session_from_disk_quarantines_empty_file(tmp_path, monkeypatch):
    monkeypatch.setattr(durable_store, "_SESSION_DIR", Path(tmp_path))

    session_path = durable_store._session_path("session_corrupt")
    session_path.write_text("", encoding="utf-8")

    with pytest.raises(durable_store.CorruptSessionPayloadError) as exc_info:
        durable_store.load_session_from_disk("session_corrupt")

    exc = exc_info.value
    assert exc.reason == "corrupt_session_payload"
    assert "session_corrupt" == exc.session_id
    assert not session_path.exists()
    quarantined = list(Path(tmp_path).glob("session_corrupt.corrupt.*.json"))
    assert quarantined, "expected corrupt session file to be quarantined"


def test_list_sessions_from_disk_skips_corrupt_files_after_quarantine(tmp_path, monkeypatch):
    monkeypatch.setattr(durable_store, "_SESSION_DIR", Path(tmp_path))

    durable_store.save_session_to_disk(_build_session("session_healthy"))

    corrupt_path = durable_store._session_path("session_broken")
    corrupt_path.write_text("{not valid json", encoding="utf-8")

    sessions = durable_store.list_sessions_from_disk()

    session_ids = {
        str((item.get("manifest") or {}).get("id") or (item.get("manifest") or {}).get("session_id"))
        for item in sessions
    }
    assert "session_healthy" in session_ids
    assert "session_broken" not in session_ids
    assert not corrupt_path.exists()
    quarantined = list(Path(tmp_path).glob("session_broken.corrupt.*.json"))
    assert quarantined, "expected invalid JSON file to be quarantined"


def test_atomic_save_does_not_leave_temp_files_behind(tmp_path, monkeypatch):
    monkeypatch.setattr(durable_store, "_SESSION_DIR", Path(tmp_path))

    durable_store.save_session_to_disk(_build_session("session_cleanup"), compact=True)

    leftovers = [p for p in Path(tmp_path).iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []
