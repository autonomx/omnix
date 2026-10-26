"""A campaign document stored in parts (roadmap §7 Q-13)."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from app.apps.rpg.foundation.persistence.document_parts import (
    HASH_PREFIX,
    PART_MIN_BYTES,
    STALE,
    assembled,
    canonical_json,
    hash_matches,
    state_hash,
    stored_form,
)

_BIG = ["Day %d: the road ran on past quiet farms." % day for day in range(400)]


def _document() -> dict:
    return {
        "manifest": {"session_id": "rpg_parts", "schema_version": 8, "notes": _BIG},
        "turn_count": 3,
        "state": {"player_journal_archive": list(_BIG), "player": {"level": 2, "notes": _BIG},
                  "a/b~c": deepcopy(_BIG), "location": "loc:square"},
        "runtime_state": {"state_revision": 3, "interaction_timeline": [{"turn": n, "text": "x" * 40} for n in range(200)]},
        "simulation_state": {"rng_seed": 7},
        "empty": {},
    }


def _stored(document: dict) -> tuple[dict, dict]:
    """The document as storage gives it back: its head decoded, its parts as rows."""
    form = stored_form(document)
    parts = {path: [digest, json.loads(text)] for path, (text, digest) in form.written.items()}
    return json.loads(form.head), parts


def test_large_entries_are_parts_and_the_head_keeps_what_sql_reads() -> None:
    form = stored_form(_document())
    head = json.loads(form.head)
    assert set(form.part_hashes) == {"/state/player_journal_archive", "/state/a~1b~0c",
                                     "/runtime_state/interaction_timeline"}
    assert all(len(text) >= PART_MIN_BYTES for text, _ in form.written.values())
    assert head["manifest"]["notes"] == _BIG  # the manifest is never split
    assert head["state"]["player"]["notes"] == _BIG  # read by the summary trigger: in the head however large
    assert head["state"]["location"] == "loc:square" and head["simulation_state"] == {"rng_seed": 7}
    assert head["empty"] == {} and "player_journal_archive" not in head["state"]


def test_the_stored_document_is_the_document_and_its_hash_does_not_depend_on_the_split() -> None:
    document = _document()
    head, parts = _stored(document)
    rebuilt, hashes = assembled(head, parts)
    assert rebuilt == document and STALE not in hashes.values()
    digest = state_hash(document)
    assert digest.startswith(HASH_PREFIX) and hash_matches(rebuilt, digest)
    whole = stored_form(json.loads(canonical_json(document)))  # stored whole, as before parts, it hashes the same
    assert whole.digest == digest
    changed = deepcopy(document)
    changed["state"]["player_journal_archive"][0] = "Day 0: rain."
    assert state_hash(changed) != digest and not hash_matches(changed, digest)
    changed = deepcopy(document)
    changed["empty"] = []
    assert state_hash(changed) != digest  # an empty section is not the same as an empty list


def test_a_write_serializes_and_stores_only_the_parts_that_changed() -> None:
    before = _document()
    head, parts = _stored(before)
    stored, stored_hashes = assembled(head, parts)
    after = deepcopy(stored)
    after["runtime_state"]["interaction_timeline"].append({"turn": 201, "text": "y"})
    after["runtime_state"]["state_revision"] = 4
    del after["state"]["a/b~c"]
    form = stored_form(after, before=stored, stored_parts=stored_hashes)
    assert set(form.written) == {"/runtime_state/interaction_timeline"}
    assert form.removed == ("/state/a~1b~0c",)
    assert form.part_hashes["/state/player_journal_archive"] == stored_hashes["/state/player_journal_archive"]
    assert form.digest == state_hash(after)


def test_an_entry_that_shrinks_returns_to_the_head_and_its_part_is_removed() -> None:
    head, parts = _stored(_document())
    stored, stored_hashes = assembled(head, parts)
    after = deepcopy(stored)
    after["state"]["player_journal_archive"] = ["Day 1."]
    form = stored_form(after, before=stored, stored_parts=stored_hashes)
    assert "/state/player_journal_archive" in form.removed and not form.written
    assert json.loads(form.head)["state"]["player_journal_archive"] == ["Day 1."]


def test_a_part_the_head_overrides_is_stale_and_rewritten() -> None:
    document = _document()
    _, parts = _stored(document)
    whole = json.loads(canonical_json(document))
    whole["state"]["player_journal_archive"] = list(reversed(_BIG))  # written whole, out of band
    rebuilt, hashes = assembled(whole, parts)
    assert rebuilt["state"]["player_journal_archive"] == list(reversed(_BIG))  # the head wins
    assert set(hashes.values()) == {STALE}  # the whole head holds every entry
    form = stored_form(rebuilt, before=rebuilt, stored_parts=hashes)
    assert set(form.written) == set(parts)  # each equal to itself, but its stored row is stale


def test_a_hash_from_before_parts_is_the_whole_texts_sha256() -> None:
    document = _document()
    legacy = hashlib.sha256(canonical_json(document).encode("utf-8")).hexdigest()
    assert hash_matches(document, legacy)
    document["turn_count"] = 4
    assert not hash_matches(document, legacy)
