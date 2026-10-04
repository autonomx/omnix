from __future__ import annotations

import json
from copy import deepcopy

from app.rpg.session.legacy_interaction_migration import (
    LEGACY_INTERACTION_MIGRATION_VERSION,
)
from app.rpg.session.migrations import migrate_session_payload


def _legacy_wrapped_payload() -> dict:
    transcript = [
        {
            "role": "player",
            "text": "I ask Bran how business is doing.",
            "turn_id": "turn:9",
            "tick": 9,
            "created_at": "2026-01-01T10:00:00Z",
        },
        {
            "role": "assistant",
            "speaker_id": "npc:bran",
            "speaker": "Bran",
            "text": "Business is steady, though the old road has been quiet.",
        },
        {
            "role": "player",
            "text": "I ask whether travelers still stop here.",
            "turn_id": "turn:10",
            "tick": 10,
        },
        {
            "role": "narrator",
            "text": "Bran glances toward the empty tables.",
        },
        {
            "role": "assistant",
            "speaker_id": "npc:bran",
            "speaker": "Bran",
            "text": "Fewer than last month, but the regulars still come through.",
        },
    ]
    return {
        "save_version": "1.0",
        "session": {
            "manifest": {
                "id": "session:legacy",
                "session_id": "session:legacy",
                "schema_version": 4,
                "turn_count": 10,
            },
            "state": {"location": "Rusty Flagon Tavern"},
            "simulation_state": {"tick": 10, "player_state": {"level": 2}},
            "runtime_state": {"transcript": transcript},
        },
    }


def test_wrapped_legacy_transcript_migrates_to_interaction_events() -> None:
    payload = _legacy_wrapped_payload()
    original_transcript = deepcopy(payload["session"]["runtime_state"]["transcript"])

    migrated = migrate_session_payload(payload)
    session = migrated["session"]
    runtime = session["runtime_state"]
    events = runtime["interaction_timeline"]["events"]

    assert session["manifest"]["schema_version"] == 5
    assert session["manifest"]["turn_count"] == 10
    assert session["simulation_state"]["tick"] == 10
    assert runtime["transcript"] == original_transcript
    assert runtime["interaction_seq"] == 2
    assert runtime["state_revision"] == 2
    assert [event["interaction_id"] for event in events] == [
        "interaction:1",
        "interaction:2",
    ]
    assert events[0]["player_input"] == "I ask Bran how business is doing."
    assert events[0]["speaker"] == "Bran"
    assert events[0]["npc_line"].startswith("Business is steady")
    assert events[0]["simulation_tick"] == 9
    assert events[1]["narration"] == "Bran glances toward the empty tables."
    assert events[1]["visible_response"]["messages"][0]["speaker_id"] == "npc:bran"
    assert runtime["legacy_interaction_migration"]["format_version"] == (
        LEGACY_INTERACTION_MIGRATION_VERSION
    )
    assert runtime["legacy_interaction_migration"]["source"] == "runtime_state.transcript"


def test_interaction_like_history_preserves_existing_sequences_and_counters() -> None:
    payload = {
        "manifest": {"id": "session:history", "schema_version": 4, "turn_count": 14},
        "simulation_state": {"tick": 14},
        "runtime_state": {
            "interaction_seq": 7,
            "state_revision": 11,
            "conversation_history": [
                {
                    "player_input": "I ask Bran about the old road.",
                    "narration": "Bran lowers his voice.",
                    "npc": {
                        "speaker_id": "npc:bran",
                        "speaker": "Bran",
                        "line": "The old road has been too quiet for market week.",
                    },
                    "turn_id": "turn:14",
                    "tick": 14,
                }
            ],
        },
    }

    migrated = migrate_session_payload(payload)
    event = migrated["runtime_state"]["interaction_timeline"]["events"][0]

    assert event["sequence"] == 7
    assert event["state_revision"] == 11
    assert event["turn_id"] == "turn:14"
    assert migrated["runtime_state"]["interaction_seq"] == 7
    assert migrated["runtime_state"]["state_revision"] == 11
    assert migrated["manifest"]["turn_count"] == 14
    assert migrated["simulation_state"]["tick"] == 14


def test_legacy_migration_is_idempotent_across_json_restart() -> None:
    first = migrate_session_payload(_legacy_wrapped_payload())
    restarted = json.loads(json.dumps(first))
    second = migrate_session_payload(restarted)

    assert second == first
    events = second["session"]["runtime_state"]["interaction_timeline"]["events"]
    assert len(events) == 2
    assert len({event["interaction_id"] for event in events}) == 2


def test_existing_modern_timeline_is_not_replaced_by_legacy_rows() -> None:
    existing = {
        "format_version": "rpg_interaction_timeline_v1",
        "interaction_id": "interaction:8",
        "sequence": 8,
        "state_revision": 12,
        "player_input": "Existing modern interaction",
        "visible_response": {"plain_text": "Existing modern response"},
    }
    payload = {
        "manifest": {"id": "session:modern", "schema_version": 4},
        "runtime_state": {
            "transcript": [{"role": "player", "text": "Legacy row"}],
            "interaction_timeline": {
                "format_version": "rpg_interaction_timeline_v1",
                "last_sequence": 8,
                "state_revision": 12,
                "events": [deepcopy(existing)],
            },
        },
    }

    migrated = migrate_session_payload(payload)
    runtime = migrated["runtime_state"]

    assert runtime["interaction_timeline"]["events"] == [existing]
    assert runtime["interaction_seq"] == 8
    assert runtime["state_revision"] == 12
    assert runtime["transcript"] == [{"role": "player", "text": "Legacy row"}]


def test_unconvertible_legacy_rows_are_marked_without_data_loss() -> None:
    rows = [None, 42, {}, []]
    payload = {
        "manifest": {"id": "session:odd", "schema_version": 4},
        "runtime_state": {"transcript": deepcopy(rows)},
    }

    first = migrate_session_payload(payload)
    second = migrate_session_payload(json.loads(json.dumps(first)))
    runtime = second["runtime_state"]

    assert runtime["transcript"] == rows
    assert "interaction_timeline" not in runtime
    assert runtime["legacy_interaction_migration"]["status"] == "no_convertible_rows"
    assert second == first
