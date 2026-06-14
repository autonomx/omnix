"""Tests for deterministic RPG memory writer schema."""
from __future__ import annotations

from copy import deepcopy

from app.rpg.session.memory_writer import (
    MEMORY_SCHEMA_VERSION,
    empty_memory_state,
    memory_state_from_session,
    write_post_turn_memory,
)


def _payload() -> dict:
    return {
        "authoritative": {
            "turn_id": "turn:7",
            "tick": 7,
            "summary": "Bran gives a quiet warning about the quarry road.",
            "location_id": "rusty_flagon",
            "action_type": "dialogue",
            "npc": {
                "id": "bran",
                "line": "Keep your eyes open near the quarry road.",
            },
        }
    }


def test_empty_memory_state_schema_is_stable():
    assert empty_memory_state() == {
        "version": MEMORY_SCHEMA_VERSION,
        "next_sequence": 1,
        "entries": [],
    }


def test_memory_state_from_session_normalizes_missing_state():
    assert memory_state_from_session({"runtime_state": {}}) == empty_memory_state()


def test_write_post_turn_memory_appends_turn_and_dialogue_entries():
    session = {"session_id": "s1", "runtime_state": {"tick": 7}}

    updated = write_post_turn_memory(
        session,
        _payload(),
        player_input="I ask Bran about the road.",
    )

    memory = updated["runtime_state"]["memory"]
    assert memory["version"] == MEMORY_SCHEMA_VERSION
    assert memory["next_sequence"] == 3
    assert [entry["id"] for entry in memory["entries"]] == ["mem:000001", "mem:000002"]
    assert [entry["kind"] for entry in memory["entries"]] == ["turn", "dialogue"]
    assert memory["entries"][0]["text"] == (
        "Player: I ask Bran about the road. | Outcome: Bran gives a quiet "
        "warning about the quarry road."
    )
    assert memory["entries"][0]["tags"] == ["turn", "dialogue"]
    assert memory["entries"][1]["actor_id"] == "bran"
    assert memory["entries"][1]["subject_id"] == "bran"
    assert memory["entries"][1]["text"] == "Keep your eyes open near the quarry road."
    assert memory["entries"][1]["tags"] == ["dialogue", "bran"]


def test_write_post_turn_memory_does_not_mutate_input_session():
    session = {"session_id": "s1", "runtime_state": {"tick": 7}}
    original = deepcopy(session)

    write_post_turn_memory(session, _payload(), player_input="I ask Bran about the road.")

    assert session == original


def test_write_post_turn_memory_continues_existing_sequence():
    session = {
        "runtime_state": {
            "memory": {
                "version": MEMORY_SCHEMA_VERSION,
                "next_sequence": 4,
                "entries": [
                    {
                        "id": "mem:000001",
                        "schema_version": MEMORY_SCHEMA_VERSION,
                        "kind": "turn",
                        "text": "Earlier memory.",
                    }
                ],
            }
        }
    }

    updated = write_post_turn_memory(session, _payload(), player_input="Any news?")
    entries = updated["runtime_state"]["memory"]["entries"]

    assert [entry["id"] for entry in entries] == [
        "mem:000001",
        "mem:000004",
        "mem:000005",
    ]
    assert updated["runtime_state"]["memory"]["next_sequence"] == 6
