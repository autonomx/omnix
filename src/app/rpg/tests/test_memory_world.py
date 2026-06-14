"""Tests for deterministic RPG world/event memory helpers."""
from __future__ import annotations

from copy import deepcopy

from app.rpg.session.memory_world import (
    get_relevant_world_memory,
    get_world_memory,
    write_world_memory,
)
from app.rpg.session.memory_writer import MEMORY_SCHEMA_VERSION


def _world_entry(
    entry_id: str,
    event_type: str,
    text: str,
    *,
    tick: int = 0,
    scope: str = "location",
    scope_id: str = "rusty_flagon",
    location_id: str = "rusty_flagon",
    visibility: str = "public",
    tags: list[str] | None = None,
) -> dict:
    return {
        "id": entry_id,
        "schema_version": MEMORY_SCHEMA_VERSION,
        "kind": "world",
        "text": text,
        "event_type": event_type,
        "scope": scope,
        "scope_id": scope_id,
        "tick": tick,
        "turn_id": f"turn:{tick}",
        "actor_id": "",
        "subject_id": "",
        "location_id": location_id,
        "visibility": visibility,
        "salience": 4,
        "tags": tags or ["world", event_type, scope, scope_id],
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


def test_missing_world_memory_returns_empty_list():
    assert get_world_memory({"runtime_state": {}}) == []
    assert get_relevant_world_memory({"runtime_state": {}}, query_terms="rumor") == []


def test_write_world_memory_appends_public_location_rumor():
    session = {"session_id": "s1", "runtime_state": {"tick": 5}}

    updated = write_world_memory(
        session,
        text="A rumor spreads in the Rusty Flagon about lights near the quarry road.",
        event_type="rumor",
        scope="location",
        scope_id="rusty_flagon",
        location_id="rusty_flagon",
        tick=5,
        turn_id="turn:5",
        tags=["quarry", "rumor", "quarry"],
    )

    assert updated["runtime_state"]["memory"]["entries"] == [
        {
            "id": "mem:000001",
            "schema_version": MEMORY_SCHEMA_VERSION,
            "kind": "world",
            "text": "A rumor spreads in the Rusty Flagon about lights near the quarry road.",
            "tick": 5,
            "turn_id": "turn:5",
            "actor_id": "",
            "subject_id": "",
            "location_id": "rusty_flagon",
            "visibility": "public",
            "salience": 4,
            "tags": ["world", "rumor", "location", "rusty_flagon", "quarry"],
            "source": "world_memory_writer",
            "event_type": "rumor",
            "scope": "location",
            "scope_id": "rusty_flagon",
        }
    ]
    assert updated["runtime_state"]["memory"]["next_sequence"] == 2


def test_write_world_memory_does_not_mutate_input_session():
    session = {"session_id": "s1", "runtime_state": {"tick": 5}}
    original = deepcopy(session)

    write_world_memory(session, text="A public rumor spreads.", event_type="rumor")

    assert session == original


def test_write_world_memory_ignores_missing_text_or_event_type():
    session = _session([_world_entry("mem:000001", "rumor", "Existing rumor.")])

    missing_text = write_world_memory(session, text="   ", event_type="rumor")
    missing_event = write_world_memory(session, text="A thing happened.", event_type="")

    assert missing_text == session
    assert missing_event == session


def test_get_world_memory_filters_scope_location_visibility_and_limit():
    session = _session(
        [
            _world_entry("mem:000001", "rumor", "Old tavern rumor.", tick=1),
            _world_entry("mem:000002", "combat", "Bandits fought near the quarry.", tick=2, location_id="quarry"),
            _world_entry("mem:000003", "rumor", "New tavern rumor.", tick=3),
            _world_entry("mem:000004", "crime", "A private theft clue.", tick=4, visibility="private"),
        ]
    )

    recent = get_world_memory(
        session,
        event_type="rumor",
        scope="location",
        location_id="rusty_flagon",
        visibility="public",
        limit=1,
    )

    assert [entry["id"] for entry in recent] == ["mem:000003"]
    assert recent[0]["text"] == "New tavern rumor."


def test_get_relevant_world_memory_matches_crime_and_quest_clues():
    session = _session(
        [
            _world_entry("mem:000001", "rumor", "Tavern talk mentions rain.", tick=1),
            _world_entry("mem:000002", "crime", "A silver locket vanished near the bar.", tick=2, tags=["world", "crime", "locket"]),
            _world_entry(
                "mem:000003",
                "quest_clue",
                "The quarry road clue points toward the old shrine.",
                tick=3,
                scope="quest",
                scope_id="missing_caravan",
                location_id="quarry",
            ),
        ]
    )

    crime_memory = get_relevant_world_memory(session, query_terms="locket")
    quest_memory = get_relevant_world_memory(session, event_type="quest_clue", scope="quest")

    assert [entry["id"] for entry in crime_memory] == ["mem:000002"]
    assert [entry["id"] for entry in quest_memory] == ["mem:000003"]


def test_malformed_world_entries_are_ignored_or_normalized_deterministically():
    session = _session(
        [
            {"kind": "world", "text": "Missing id.", "event_type": "rumor"},
            _world_entry("mem:000001", "", "Missing event type."),
            _world_entry(
                "mem:000002",
                "combat",
                " Bandits   scattered near the quarry. ",
                tick=-1,
                scope="town",
                scope_id="",
                location_id="quarry",
                visibility="secret",
                tags=["World", "COMBAT", "COMBAT", 7],
            ),
        ]
    )

    assert get_world_memory(session, event_type="combat") == [
        {
            "id": "mem:000002",
            "schema_version": MEMORY_SCHEMA_VERSION,
            "kind": "world",
            "text": "Bandits scattered near the quarry.",
            "event_type": "combat",
            "scope": "location",
            "scope_id": "",
            "tick": 0,
            "turn_id": "turn:-1",
            "actor_id": "",
            "subject_id": "",
            "location_id": "quarry",
            "visibility": "public",
            "salience": 4,
            "tags": ["world", "combat", "7"],
            "source": "test",
        }
    ]


def test_world_memory_sequences_remain_stable_across_event_types():
    session = {"runtime_state": {}}

    with_combat = write_world_memory(
        session,
        text="A public brawl breaks out near the quarry road.",
        event_type="combat",
        location_id="quarry",
    )
    with_clue = write_world_memory(
        with_combat,
        text="A caravan track points toward the old shrine.",
        event_type="quest_clue",
        scope="quest",
        scope_id="missing_caravan",
        location_id="quarry",
    )

    assert [entry["id"] for entry in get_world_memory(with_clue, event_type="combat")] == ["mem:000001"]
    assert [entry["id"] for entry in get_world_memory(with_clue, event_type="quest_clue")] == ["mem:000002"]
    assert with_clue["runtime_state"]["memory"]["next_sequence"] == 3
