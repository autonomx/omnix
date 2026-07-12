from __future__ import annotations

import json
from pathlib import Path

from app.rpg.session import durable_store
from app.rpg.session.interaction_event_store import (
    INTERACTION_COMPACTION_EVENT_COUNT,
    append_interaction_event,
    compact_interaction_event_log,
    interaction_event_log_path,
    interaction_event_log_status,
    interaction_log_requires_compaction,
    load_and_replay_interaction_events,
    load_interaction_events,
)


def _event(sequence: int, *, stateful: bool = False) -> dict:
    return {
        "format_version": "rpg_interaction_timeline_v1",
        "interaction_id": f"interaction:{sequence}",
        "sequence": sequence,
        "state_revision": sequence,
        "simulation_tick": 0 if not stateful else sequence,
        "kind": "npc_dialogue" if not stateful else "trade",
        "stateful": stateful,
        "player_input": f"Question {sequence}",
        "npc_line": f"Answer {sequence}",
    }


def _session() -> dict:
    return {
        "manifest": {
            "id": "session:event-store",
            "session_id": "session:event-store",
            "title": "Event Store",
            "schema_version": 2,
        },
        "state": {},
        "simulation_state": {"tick": 0},
        "runtime_state": {"tick": 0},
        "installed_packs": [],
    }


def test_append_only_events_round_trip_with_checksums(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(durable_store, "_SESSION_DIR", tmp_path)

    append_interaction_event("session:event-store", _event(1))
    append_interaction_event("session:event-store", _event(2))

    events = load_interaction_events("session:event-store")
    assert [event["sequence"] for event in events] == [1, 2]
    assert load_interaction_events("session:event-store", after_sequence=1) == [_event(2)]
    status = interaction_event_log_status("session:event-store")
    assert status["exists"] is True
    assert status["event_count"] == 2
    assert status["size_bytes"] > 0


def test_invalid_or_tampered_event_lines_are_ignored(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(durable_store, "_SESSION_DIR", tmp_path)
    append_interaction_event("session:event-store", _event(1))
    path = interaction_event_log_path("session:event-store")
    path.write_text(
        path.read_text(encoding="utf-8")
        + json.dumps(
            {
                "format_version": "rpg_interaction_event_log_v1",
                "checksum": "wrong",
                "event": _event(2),
            }
        )
        + "\n{not-json\n",
        encoding="utf-8",
    )

    assert load_interaction_events("session:event-store") == [_event(1)]


def test_stale_snapshot_replays_newer_events_without_duplicates(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(durable_store, "_SESSION_DIR", tmp_path)
    session = _session()
    session["runtime_state"] = {
        "interaction_seq": 1,
        "state_revision": 1,
        "interaction_timeline": {
            "last_sequence": 1,
            "state_revision": 1,
            "events": [_event(1)],
        },
    }
    append_interaction_event("session:event-store", _event(1))
    append_interaction_event("session:event-store", _event(2))
    append_interaction_event("session:event-store", _event(3))

    replayed = load_and_replay_interaction_events("session:event-store", session)
    timeline = replayed["runtime_state"]["interaction_timeline"]

    assert [event["sequence"] for event in timeline["events"]] == [1, 2, 3]
    assert replayed["runtime_state"]["interaction_seq"] == 3
    assert replayed["runtime_state"]["state_revision"] == 3


def test_event_log_compaction_keeps_only_events_after_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(durable_store, "_SESSION_DIR", tmp_path)
    for sequence in range(1, 6):
        append_interaction_event("session:event-store", _event(sequence))

    remaining = compact_interaction_event_log("session:event-store", through_sequence=3)

    assert remaining == 2
    assert [event["sequence"] for event in load_interaction_events("session:event-store")] == [4, 5]
    assert not list(tmp_path.glob("*.tmp"))


def test_compaction_policy_bounds_event_log_growth(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(durable_store, "_SESSION_DIR", tmp_path)
    for sequence in range(1, INTERACTION_COMPACTION_EVENT_COUNT + 1):
        append_interaction_event("session:event-store", _event(sequence))

    assert interaction_log_requires_compaction("session:event-store") is True
