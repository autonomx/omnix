"""The turns' narrations come out of the document when it is stored and go back when it is loaded (RQ-1.4)."""
from __future__ import annotations

from app.apps.rpg.foundation.persistence.turn_narrations import split_turn_narrations, with_turn_narrations


def test_split_takes_both_copies_out_and_the_turns_entry_wins() -> None:
    listed = {"turn_id": "turn:1", "narration": "old"}
    document = {"runtime_state": {"tick": 3, "narration_artifacts": [listed, "junk"],
                                  "narration_artifacts_by_turn": {"turn:1": {"turn_id": "turn:1", "narration": "new"}}}}
    stored, narrations = split_turn_narrations(document)
    assert stored["runtime_state"] == {"tick": 3}
    assert narrations == {"turn:1": {"turn_id": "turn:1", "narration": "new"}}


def test_a_document_without_narrations_is_left_as_it_is() -> None:
    document = {"runtime_state": {"tick": 3}}
    assert split_turn_narrations(document) == (document, {})


def test_loading_puts_the_kept_narrations_back_after_any_the_document_still_has() -> None:
    document = {"runtime_state": {"narration_artifacts": [{"turn_id": "turn:0", "narration": "legacy"}],
                                  "narration_artifacts_by_turn": {"turn:0": {"turn_id": "turn:0"}}}}
    loaded = with_turn_narrations(document, [("turn:1", {"turn_id": "turn:1", "narration": "a"})])
    runtime = loaded["runtime_state"]
    assert [artifact["turn_id"] for artifact in runtime["narration_artifacts"]] == ["turn:0", "turn:1"]
    assert set(runtime["narration_artifacts_by_turn"]) == {"turn:0", "turn:1"}
    assert with_turn_narrations({"runtime_state": {}}, []) == {"runtime_state": {}}
