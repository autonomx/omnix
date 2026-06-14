"""Tests for deterministic RPG actor memory helpers."""
from __future__ import annotations

from copy import deepcopy

from app.rpg.session.memory_actor import (
    get_actor_memory,
    get_relevant_actor_memory,
    write_actor_memory,
)
from app.rpg.session.memory_writer import MEMORY_SCHEMA_VERSION


def _actor_entry(
    entry_id: str,
    actor_id: str,
    text: str,
    *,
    tick: int = 0,
    subject_id: str = "player",
    visibility: str = "private",
    tags: list[str] | None = None,
    relationship: dict | None = None,
) -> dict:
    entry = {
        "id": entry_id,
        "schema_version": MEMORY_SCHEMA_VERSION,
        "kind": "actor",
        "text": text,
        "tick": tick,
        "turn_id": f"turn:{tick}",
        "actor_id": actor_id,
        "subject_id": subject_id,
        "location_id": "rusty_flagon",
        "visibility": visibility,
        "salience": 5,
        "tags": tags or ["actor", actor_id, subject_id],
        "source": "test",
    }
    if relationship is not None:
        entry["relationship"] = relationship
    return entry


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


def test_missing_actor_memory_returns_empty_list():
    assert get_actor_memory({"runtime_state": {}}, "bran") == []
    assert get_relevant_actor_memory({"runtime_state": {}}, "bran", query_terms="quarry") == []


def test_write_actor_memory_appends_bran_private_relationship_memory():
    session = {"session_id": "s1", "runtime_state": {"tick": 3}}

    updated = write_actor_memory(
        session,
        actor_id="bran",
        subject_id="player",
        text="Bran remembers that the player paid for stew without haggling.",
        relationship={"target_id": "player", "axes": {"trust": 2, "familiarity": 1}, "stance": "warming"},
        tick=3,
        turn_id="turn:3",
        location_id="rusty_flagon",
        tags=["stew", "commerce", "stew"],
    )

    memory = updated["runtime_state"]["memory"]
    assert memory["next_sequence"] == 2
    assert memory["entries"] == [
        {
            "id": "mem:000001",
            "schema_version": MEMORY_SCHEMA_VERSION,
            "kind": "actor",
            "text": "Bran remembers that the player paid for stew without haggling.",
            "tick": 3,
            "turn_id": "turn:3",
            "actor_id": "bran",
            "subject_id": "player",
            "location_id": "rusty_flagon",
            "visibility": "private",
            "salience": 5,
            "tags": ["actor", "bran", "player", "stew", "commerce"],
            "source": "actor_memory_writer",
            "relationship": {
                "target_id": "player",
                "stance": "warming",
                "axes": {"familiarity": 1, "trust": 2},
            },
        }
    ]


def test_write_actor_memory_does_not_mutate_input_session():
    session = {"session_id": "s1", "runtime_state": {"tick": 3}}
    original = deepcopy(session)

    write_actor_memory(session, actor_id="bran", text="Bran remembers a paid meal.")

    assert session == original


def test_write_actor_memory_ignores_empty_actor_or_text_but_preserves_memory_state():
    session = _session([_actor_entry("mem:000001", "bran", "Existing memory.")])

    missing_actor = write_actor_memory(session, actor_id="", text="No actor.")
    missing_text = write_actor_memory(session, actor_id="bran", text="   ")

    assert missing_actor == session
    assert missing_text == session


def test_get_actor_memory_filters_actor_subject_visibility_and_limit():
    session = _session(
        [
            _actor_entry("mem:000001", "bran", "Bran remembers the first meal.", tick=1),
            _actor_entry("mem:000002", "elara", "Elara remembers the ledger.", tick=2, visibility="public"),
            _actor_entry("mem:000003", "bran", "Bran remembers the quarry warning.", tick=3),
            _actor_entry("mem:000004", "bran", "Bran tells Elara about stew.", tick=4, subject_id="elara"),
        ]
    )

    recent = get_actor_memory(session, "bran", subject_id="player", visibility="private", limit=1)

    assert [entry["id"] for entry in recent] == ["mem:000003"]
    assert recent[0]["text"] == "Bran remembers the quarry warning."


def test_get_relevant_actor_memory_matches_text_tags_and_relationship_metadata():
    session = _session(
        [
            _actor_entry("mem:000001", "bran", "Bran remembers the first meal.", tick=1),
            _actor_entry(
                "mem:000002",
                "bran",
                "Bran trusts the player near the quarry road.",
                tick=2,
                relationship={"target_id": "player", "axes": {"trust": 2}},
            ),
            _actor_entry("mem:000003", "bran", "Bran notes a tavern rumor.", tick=3, tags=["actor", "bran", "rumor"]),
        ]
    )

    trust_memory = get_relevant_actor_memory(session, "bran", query_terms=["trust"])
    rumor_memory = get_relevant_actor_memory(session, "bran", query_terms="rumor")

    assert [entry["id"] for entry in trust_memory] == ["mem:000002"]
    assert [entry["id"] for entry in rumor_memory] == ["mem:000003"]


def test_malformed_actor_entries_are_ignored_or_normalized_deterministically():
    session = _session(
        [
            {"kind": "actor", "text": "Missing id."},
            _actor_entry("mem:000001", "", "Missing actor."),
            _actor_entry(
                "mem:000002",
                "elara",
                " Elara   remembers the ledger. ",
                tick=-1,
                visibility="town",
                tags=["Actor", "ELARA", "ELARA", 7],
                relationship={"target_id": "player", "axes": {"trust": 1.23456, "ignored": True}},
            ),
        ]
    )

    assert get_actor_memory(session, "elara") == [
        {
            "id": "mem:000002",
            "schema_version": MEMORY_SCHEMA_VERSION,
            "kind": "actor",
            "text": "Elara remembers the ledger.",
            "tick": 0,
            "turn_id": "turn:-1",
            "actor_id": "elara",
            "subject_id": "player",
            "location_id": "rusty_flagon",
            "visibility": "private",
            "salience": 5,
            "tags": ["actor", "elara", "7"],
            "source": "test",
            "relationship": {"target_id": "player", "axes": {"trust": 1.2346}},
        }
    ]


def test_bran_and_elara_memory_sequences_remain_stable():
    session = {"runtime_state": {}}

    with_bran = write_actor_memory(
        session,
        actor_id="bran",
        text="Bran remembers the player bought stew.",
        relationship={"target_id": "player", "axes": {"familiarity": 1}},
    )
    with_elara = write_actor_memory(
        with_bran,
        actor_id="elara",
        text="Elara remembers the player asked about the ledger.",
        relationship={"target_id": "player", "axes": {"trust": 1}},
        visibility="public",
    )

    assert [entry["id"] for entry in get_actor_memory(with_elara, "bran")] == ["mem:000001"]
    assert [entry["id"] for entry in get_actor_memory(with_elara, "elara")] == ["mem:000002"]
    assert with_elara["runtime_state"]["memory"]["next_sequence"] == 3
