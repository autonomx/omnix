"""Tests for deterministic RPG memory aging and compaction."""
from __future__ import annotations

from copy import deepcopy

from app.rpg.session.memory_aging import (
    MEMORY_AGING_VERSION,
    age_and_compact_memory,
    reinforce_memory_entries,
)
from app.rpg.session.memory_retrieval import get_relevant_recent_memory
from app.rpg.session.memory_writer import MEMORY_SCHEMA_VERSION


def _entry(
    entry_id: str,
    kind: str,
    text: str,
    *,
    tick: int,
    salience: int,
    actor_id: str = "",
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
        "subject_id": actor_id,
        "location_id": "rusty_flagon",
        "visibility": "public",
        "salience": salience,
        "tags": tags or [kind],
        "source": "test",
    }


def _session(entries: list[dict], next_sequence: int | None = None) -> dict:
    return {
        "session_id": "memory-aging",
        "runtime_state": {
            "memory": {
                "version": MEMORY_SCHEMA_VERSION,
                "next_sequence": next_sequence or len(entries) + 1,
                "entries": entries,
            }
        },
    }


def test_reinforce_memory_entries_increases_salience_without_mutating_input():
    session = _session(
        [
            _entry("mem:000001", "turn", "Asked Bran about the quarry.", tick=2, salience=3),
            _entry("mem:000002", "dialogue", "Bran warned about the quarry.", tick=2, salience=4),
        ]
    )
    original = deepcopy(session)

    updated = reinforce_memory_entries(
        session,
        ["mem:000001", "missing"],
        amount=3,
        current_tick=12,
    )

    memory = updated["runtime_state"]["memory"]
    assert memory["entries"][0]["salience"] == 6
    assert memory["entries"][0]["reinforcement_count"] == 1
    assert memory["entries"][0]["last_reinforced_tick"] == 12
    assert memory["entries"][1]["salience"] == 4
    assert updated["runtime_state"]["memory_aging"] == {
        "format_version": MEMORY_AGING_VERSION,
        "source": "memory_aging",
        "operation": "reinforce",
        "current_tick": 12,
        "target_ids": ["mem:000001", "missing"],
        "reinforced_count": 1,
    }
    assert session == original


def test_age_and_compact_memory_replaces_old_low_salience_entries_with_recap():
    session = _session(
        [
            _entry("mem:000001", "turn", "First quarry question.", tick=0, salience=1),
            _entry("mem:000002", "dialogue", "Bran gave a first warning.", tick=1, salience=2),
            _entry("mem:000003", "turn", "Second tavern question.", tick=2, salience=1),
            _entry("mem:000004", "dialogue", "Bran repeated a fresh warning.", tick=18, salience=7),
            _entry("mem:000005", "actor", "Bran trusts the player.", tick=19, salience=8),
        ],
        next_sequence=6,
    )

    updated = age_and_compact_memory(session, current_tick=25, active_limit=4, decay_tick_interval=10)
    memory = updated["runtime_state"]["memory"]
    entries = memory["entries"]

    assert [entry["id"] for entry in entries] == ["mem:000003", "mem:000004", "mem:000005", "mem:000006"]
    assert entries[0]["salience"] == 0
    assert entries[1]["salience"] == 7
    assert entries[-1]["kind"] == "recap"
    assert entries[-1]["compressed_entry_ids"] == ["mem:000001", "mem:000002"]
    assert "mem:000001 turn: First quarry question." in entries[-1]["text"]
    assert memory["next_sequence"] == 7
    assert updated["runtime_state"]["memory_aging"]["compacted_count"] == 2
    assert updated["runtime_state"]["memory_aging"]["recap_id"] == "mem:000006"


def test_compacted_recap_memory_remains_retrievable_for_prompt_context():
    session = _session(
        [
            _entry("mem:000001", "turn", "Player found a brass key in the quarry.", tick=0, salience=1, tags=["quarry"]),
            _entry("mem:000002", "dialogue", "Bran said the brass key fits the shrine.", tick=1, salience=1, actor_id="bran", tags=["shrine"]),
            _entry("mem:000003", "dialogue", "Elara asked about lamp oil.", tick=8, salience=5, actor_id="elara", tags=["shop"]),
            _entry("mem:000004", "turn", "Player rested at the tavern.", tick=9, salience=5, tags=["rest"]),
        ],
        next_sequence=5,
    )

    updated = age_and_compact_memory(session, current_tick=30, active_limit=3, decay_tick_interval=10)
    relevant = get_relevant_recent_memory(updated, query_terms=["brass", "key"], limit=4)

    assert [entry["kind"] for entry in relevant] == ["recap"]
    assert relevant[0]["id"] == "mem:000005"
    assert "brass key" in relevant[0]["text"]
    assert relevant[0]["source"] == "memory_aging"


def test_age_and_compact_memory_does_not_mutate_input_and_is_stable():
    session = _session(
        [
            _entry("mem:000001", "turn", "Old low-value tavern detail.", tick=1, salience=1),
            _entry("mem:000002", "dialogue", "Old low-value tavern line.", tick=2, salience=1),
            _entry("mem:000003", "turn", "Fresh quest clue.", tick=20, salience=6, tags=["quest"]),
        ],
        next_sequence=4,
    )
    original = deepcopy(session)

    first = age_and_compact_memory(session, current_tick=30, active_limit=2, decay_tick_interval=10)
    second = age_and_compact_memory(deepcopy(session), current_tick=30, active_limit=2, decay_tick_interval=10)

    assert first == second
    assert session == original
    assert first["runtime_state"]["memory"]["entries"][-1]["kind"] == "recap"
    assert first["runtime_state"]["memory_aging"]["format_version"] == MEMORY_AGING_VERSION
