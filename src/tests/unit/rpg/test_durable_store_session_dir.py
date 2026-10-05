from pathlib import Path

from app.rpg.session import durable_store


def test_explicit_session_dir_round_trips_without_changing_default_authority(
    tmp_path: Path,
) -> None:
    default_session_dir = durable_store._SESSION_DIR
    session = {
        "manifest": {
            "id": "focused-session-dir",
            "session_id": "focused-session-dir",
            "title": "Focused session directory test",
        },
        "simulation_state": {"turn_index": 7},
    }

    durable_store.save_session_to_disk(
        session,
        compact=True,
        session_dir=tmp_path,
    )
    loaded = durable_store.load_session_from_disk(
        "focused-session-dir",
        session_dir=tmp_path,
    )

    assert loaded is not None
    assert loaded["manifest"]["session_id"] == "focused-session-dir"
    assert loaded["simulation_state"]["turn_index"] == 7
    assert (tmp_path / "focused-session-dir.json").exists()
    assert durable_store._SESSION_DIR == default_session_dir
