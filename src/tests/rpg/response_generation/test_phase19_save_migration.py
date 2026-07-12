from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from app.rpg.release_gates import evaluate_session_release_gates
from app.rpg.session import durable_store
from app.rpg.session.migrations import migrate_session_payload


def _legacy_session() -> dict:
    return {
        "manifest": {
            "id": "session:migration",
            "session_id": "session:migration",
            "schema_version": 4,
            "turn_count": 27,
        },
        "simulation_state": {"tick": 27, "presentation_state": {}, "memory_state": {}},
        "runtime_state": {
            "interaction_seq": 0,
            "state_revision": 0,
            "dialogue_history": [
                {
                    "player_input": "How is business?",
                    "speaker": "Bran",
                    "npc_line": "Steady enough, though the road is quiet.",
                    "turn_id": "turn:26",
                    "tick": 26,
                },
                {
                    "player_input": "Did anyone pass before dawn?",
                    "speaker": "Bran",
                    "npc_line": "One rider, heading north in a hurry.",
                    "turn_id": "turn:27",
                    "tick": 27,
                },
            ],
        },
    }


def test_legacy_save_load_save_restart_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(durable_store, "_SESSION_DIR", tmp_path)
    legacy = _legacy_session()
    path = durable_store._session_path("session:migration")
    path.write_text(
        json.dumps({"save_version": "1.0", "session": legacy}, ensure_ascii=False),
        encoding="utf-8",
    )

    loaded = durable_store.load_session_from_disk("session:migration")
    assert loaded is not None
    runtime = loaded["runtime_state"]
    events = runtime["interaction_timeline"]["events"]

    assert loaded["manifest"]["schema_version"] == 5
    assert loaded["manifest"]["turn_count"] == 27
    assert loaded["simulation_state"]["tick"] == 27
    assert runtime["interaction_seq"] == 2
    assert runtime["state_revision"] == 2
    assert [event["turn_id"] for event in events] == ["turn:26", "turn:27"]
    assert "dialogue_history" not in runtime
    assert evaluate_session_release_gates(loaded)["ok"] is True

    durable_store.save_session_to_disk(loaded, compact=True)
    restarted = durable_store.load_session_from_disk("session:migration")

    assert restarted == loaded
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["session"] == loaded


def test_migration_does_not_mutate_input_and_is_repeatable() -> None:
    legacy = _legacy_session()
    untouched = deepcopy(legacy)

    first = migrate_session_payload(legacy)
    second = migrate_session_payload(first)

    assert legacy == untouched
    assert first == second
    assert len(first["runtime_state"]["interaction_timeline"]["events"]) == 2
