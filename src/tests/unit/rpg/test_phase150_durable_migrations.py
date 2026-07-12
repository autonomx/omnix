"""Unit tests for durable session and interaction migrations."""
from __future__ import annotations

from copy import deepcopy

from app.rpg.session.migrations import migrate_session_payload


def test_migrate_session_payload_preserves_save_envelope() -> None:
    payload = {
        "save_version": "1.0",
        "session": {"manifest": {"id": "s1", "schema_version": 2}},
    }

    result = migrate_session_payload(payload)

    assert result["save_version"] == "1.0"
    assert result["session"]["manifest"]["id"] == "s1"
    assert result["session"]["manifest"]["schema_version"] == 5


def test_migrate_session_payload_handles_unversioned_direct_session() -> None:
    result = migrate_session_payload({"session": {}})

    assert result["manifest"]["id"] == "session:unknown"
    assert result["manifest"]["schema_version"] == 5
    assert "presentation_state" in result["simulation_state"]
    assert "memory_state" in result["simulation_state"]
    assert result["runtime_state"]["interaction_seq"] == 0
    assert result["runtime_state"]["state_revision"] == 0


def test_migrate_session_payload_sets_missing_manifest_id_and_roots() -> None:
    payload = {"manifest": {}, "simulation_state": {}}

    out = migrate_session_payload(payload)

    assert out["manifest"]["id"] == "session:unknown"
    assert out["manifest"]["schema_version"] == 5
    assert "presentation_state" in out["simulation_state"]
    assert "memory_state" in out["simulation_state"]
    assert out["runtime_state"]["interaction_timeline"]["events"] == []


def test_legacy_string_transcript_becomes_interaction_events() -> None:
    payload = {
        "manifest": {"id": "session:bran", "turn_count": 9, "schema_version": 4},
        "simulation_state": {"tick": 9},
        "runtime_state": {
            "transcript": [
                "You: How is business?",
                "Bran: Steady enough, though the road has been quiet.",
                "You: Did the guards stop here?",
                "Bran: Not since yesterday morning.",
            ],
        },
    }

    migrated = migrate_session_payload(payload)
    runtime = migrated["runtime_state"]
    events = runtime["interaction_timeline"]["events"]

    assert migrated["manifest"]["turn_count"] == 9
    assert migrated["simulation_state"]["tick"] == 9
    assert runtime["interaction_seq"] == 2
    assert runtime["state_revision"] == 2
    assert [event["interaction_id"] for event in events] == ["interaction:1", "interaction:2"]
    assert events[0]["player_input"] == "How is business?"
    assert events[0]["speaker"] == "Bran"
    assert events[0]["npc_line"] == "Steady enough, though the road has been quiet."
    assert events[1]["player_input"] == "Did the guards stop here?"
    assert "transcript" not in runtime
    assert runtime["legacy_interaction_migration"]["migrated_count"] == 2


def test_legacy_dict_transcript_preserves_turn_and_simulation_metadata() -> None:
    payload = {
        "manifest": {"id": "session:bran"},
        "dialogue_history": [
            {
                "player_input": "What did you notice?",
                "speaker": "Bran",
                "npc_line": "A rider passed before dawn.",
                "turn_id": "turn:12",
                "tick": 12,
                "state_revision": 17,
                "submission_id": "submit:legacy",
            }
        ],
    }

    migrated = migrate_session_payload(payload)
    event = migrated["runtime_state"]["interaction_timeline"]["events"][0]

    assert event["turn_id"] == "turn:12"
    assert event["simulation_tick"] == 12
    assert event["state_revision"] == 17
    assert event["submission_id"] == "submit:legacy"
    assert migrated["runtime_state"]["state_revision"] == 17
    assert "dialogue_history" not in migrated


def test_existing_timeline_wins_and_removes_redundant_legacy_transcript() -> None:
    payload = {
        "manifest": {"id": "session:existing", "schema_version": 5},
        "runtime_state": {
            "interaction_seq": 7,
            "state_revision": 11,
            "transcript": ["You: duplicate", "Bran: duplicate"],
            "interaction_timeline": {
                "last_sequence": 7,
                "state_revision": 11,
                "events": [
                    {"interaction_id": "interaction:7", "sequence": 7, "state_revision": 11}
                ],
            },
        },
    }

    migrated = migrate_session_payload(payload)
    runtime = migrated["runtime_state"]

    assert len(runtime["interaction_timeline"]["events"]) == 1
    assert runtime["interaction_timeline"]["events"][0]["interaction_id"] == "interaction:7"
    assert runtime["interaction_seq"] == 7
    assert runtime["state_revision"] == 11
    assert "transcript" not in runtime


def test_migration_repairs_duplicate_sequences_and_is_idempotent() -> None:
    payload = {
        "manifest": {"id": "session:repair", "schema_version": 4},
        "runtime_state": {
            "interaction_timeline": {
                "events": [
                    {"interaction_id": "legacy:a", "sequence": 2},
                    {"interaction_id": "legacy:b", "sequence": 2},
                    {"interaction_id": "legacy:c", "sequence": 0},
                ]
            }
        },
    }

    first = migrate_session_payload(payload)
    second = migrate_session_payload(deepcopy(first))
    events = first["runtime_state"]["interaction_timeline"]["events"]

    assert [event["sequence"] for event in events] == [2, 3, 4]
    assert [event["interaction_id"] for event in events] == ["legacy:a", "legacy:b", "legacy:c"]
    assert first == second
