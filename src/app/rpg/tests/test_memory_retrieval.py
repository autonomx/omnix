"""Tests for deterministic RPG memory retrieval helpers."""
from __future__ import annotations

from copy import deepcopy

from app.rpg.session.memory_retrieval import (
    get_recent_dialogue_memory,
    get_recent_turn_memory,
    get_relevant_recent_memory,
)
from app.rpg.session.memory_writer import MEMORY_SCHEMA_VERSION, write_post_turn_memory


def _entry(
    entry_id: str,
    kind: str,
    text: str,
    *,
    tick: int = 0,
    actor_id: str = "",
    subject_id: str = "",
    location_id: str = "",
    tags: list[str] | None = None,
) -> dict:
    return {
        "id": entry_id,
        "schema_version": MEMORY_SCHEMA_VERSION,
        "kind": kind,
        "text": text,
        "tick": tick,
        "turn_id": f"turn:{tick}",
        "actor_id": actor_id,
        "subject_id": subject_id,
        "location_id": location_id,
        "visibility": "public",
        "salience": 3,
        "tags": tags or [],
        "source": "test",
    }


def _session(entries: list[dict]) -> dict:
    return {
        "runtime_state": {
            "memory": {
                "version": MEMORY_SCHEMA_VERSION,
                "next_sequence": len(entries) + 1,
                "entries": entries,
            }
        }
    }


def _payload(npc_id: str = "bran", line: str = "Keep your eyes open near the quarry road.") -> dict:
    return {
        "authoritative": {
            "turn_id": "turn:7",
            "tick": 7,
            "summary": "Bran gives a quiet warning about the quarry road.",
            "location_id": "rusty_flagon",
            "action_type": "dialogue",
            "npc": {"id": npc_id, "line": line},
        }
    }


def test_missing_memory_returns_empty_lists():
    session = {"runtime_state": {}}

    assert get_recent_turn_memory(session) == []
    assert get_recent_dialogue_memory(session) == []
    assert get_relevant_recent_memory(session) == []


def test_recent_turn_memory_limits_entries_oldest_to_newest():
    session = _session(
        [
            _entry("mem:000001", "turn", "First turn.", tick=1),
            _entry("mem:000002", "dialogue", "A greeting.", tick=1, actor_id="bran"),
            _entry("mem:000003", "turn", "Second turn.", tick=2),
            _entry("mem:000004", "turn", "Third turn.", tick=3),
        ]
    )

    recent = get_recent_turn_memory(session, limit=2)

    assert [entry["id"] for entry in recent] == ["mem:000003", "mem:000004"]
    assert [entry["text"] for entry in recent] == ["Second turn.", "Third turn."]


def test_recent_dialogue_memory_filters_by_npc_id():
    session = _session(
        [
            _entry("mem:000001", "dialogue", "Bran remembers the road.", tick=1, actor_id="bran"),
            _entry("mem:000002", "dialogue", "Elara mentions the ledger.", tick=2, actor_id="elara"),
            _entry(
                "mem:000003",
                "dialogue",
                "Bran repeats the quarry warning.",
                tick=3,
                subject_id="bran",
            ),
        ]
    )

    recent = get_recent_dialogue_memory(session, npc_id="bran")

    assert [entry["id"] for entry in recent] == ["mem:000001", "mem:000003"]


def test_retrieval_preserves_stable_ids_and_order():
    session = _session(
        [
            _entry("mem:000001", "turn", "Asked about supper.", tick=1),
            _entry("mem:000002", "dialogue", "Bran offered stew.", tick=2, actor_id="bran"),
            _entry("mem:000003", "turn", "Paid for stew.", tick=3),
        ]
    )

    recent = get_relevant_recent_memory(session, limit=3)

    assert [entry["id"] for entry in recent] == ["mem:000001", "mem:000002", "mem:000003"]
    assert [entry["turn_id"] for entry in recent] == ["turn:1", "turn:2", "turn:3"]


def test_malformed_entries_are_ignored_or_normalized_deterministically():
    session = _session(
        [
            {"kind": "turn", "text": "Missing id is ignored."},
            _entry("mem:000001", "world", "Wrong kind is ignored."),
            _entry("mem:000002", "turn", "  Valid   turn memory.  ", tick=-1, tags=["Turn", "TURN", 7]),
            {
                "id": 3,
                "kind": "dialogue",
                "text": " Bran   speaks. ",
                "actor_id": "bran",
                "tags": "dialogue",
                "salience": "high",
            },
        ]
    )

    recent = get_relevant_recent_memory(session)

    assert recent == [
        {
            "id": "mem:000002",
            "schema_version": MEMORY_SCHEMA_VERSION,
            "kind": "turn",
            "text": "Valid turn memory.",
            "tick": 0,
            "turn_id": "turn:-1",
            "actor_id": "",
            "subject_id": "",
            "location_id": "",
            "visibility": "public",
            "salience": 3,
            "tags": ["turn", "7"],
            "source": "test",
        },
        {
            "id": "3",
            "schema_version": MEMORY_SCHEMA_VERSION,
            "kind": "dialogue",
            "text": "Bran speaks.",
            "tick": 0,
            "turn_id": "",
            "actor_id": "bran",
            "subject_id": "",
            "location_id": "",
            "visibility": "public",
            "salience": 0,
            "tags": [],
            "source": "",
        },
    ]


def test_retrieval_does_not_mutate_session():
    session = _session([_entry("mem:000001", "turn", "Original memory.", tick=1)])
    original = deepcopy(session)

    get_recent_turn_memory(session)
    get_recent_dialogue_memory(session)
    get_relevant_recent_memory(session, query_terms=["original"])

    assert session == original


def test_relevant_recent_memory_matches_query_terms_and_npc():
    session = _session(
        [
            _entry("mem:000001", "turn", "The quarry road was quiet.", tick=1),
            _entry("mem:000002", "dialogue", "Elara knows the ledger.", tick=2, actor_id="elara"),
            _entry("mem:000003", "dialogue", "Bran remembers the road.", tick=3, actor_id="bran"),
            _entry("mem:000004", "turn", "The tavern crowd cheered.", tick=4),
        ]
    )

    recent = get_relevant_recent_memory(session, npc_id="bran", query_terms=["ledger"])

    assert [entry["id"] for entry in recent] == ["mem:000002", "mem:000003"]


def test_writer_and_retriever_integration():
    session = {"session_id": "s1", "runtime_state": {"tick": 7}}

    updated = write_post_turn_memory(session, _payload(), player_input="I ask Bran about the road.")

    turn_memory = get_recent_turn_memory(updated)
    dialogue_memory = get_recent_dialogue_memory(updated, npc_id="bran")
    relevant_memory = get_relevant_recent_memory(updated, npc_id="bran", query_terms="quarry")

    assert [entry["id"] for entry in turn_memory] == ["mem:000001"]
    assert turn_memory[0]["text"].startswith("Player: I ask Bran about the road.")
    assert [entry["id"] for entry in dialogue_memory] == ["mem:000002"]
    assert [entry["id"] for entry in relevant_memory] == ["mem:000001", "mem:000002"]
