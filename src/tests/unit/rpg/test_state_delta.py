"""The per-turn JSON Patch reproduces the state it describes (WP-5.6)."""
from __future__ import annotations

import copy

from app.apps.rpg.foundation.persistence.state_delta import apply_state_delta, state_delta


def _round_trip(before, after):
    delta = state_delta(before, after)
    original = copy.deepcopy(before)
    assert apply_state_delta(before, delta) == after
    assert before == original  # applying never mutates the input
    return delta


def test_equal_states_have_an_empty_patch() -> None:
    state = {"player": {"hp": 10}, "log": ["a"]}
    assert state_delta(state, copy.deepcopy(state)) == []


def test_changed_added_and_removed_keys_are_patched_at_their_paths() -> None:
    before = {"player": {"hp": 10, "mp": 3}, "scene": {"name": "Harbor"}}
    after = {"player": {"hp": 7, "xp": 5}, "scene": {"name": "Harbor"}}
    delta = _round_trip(before, after)
    assert sorted((op["op"], op["path"]) for op in delta) == [
        ("add", "/player/xp"), ("remove", "/player/mp"), ("replace", "/player/hp"),
    ]


def test_keys_with_slash_and_tilde_are_escaped() -> None:
    before = {"npcs": {"npc:a/b": {"mood": "calm"}, "x~y": 1}}
    after = {"npcs": {"npc:a/b": {"mood": "angry"}, "x~y": 2}}
    delta = _round_trip(before, after)
    assert {op["path"] for op in delta} == {"/npcs/npc:a~1b/mood", "/npcs/x~0y"}


def test_a_list_that_grew_at_its_end_gets_appends() -> None:
    before = {"log": [{"turn": 1}, {"turn": 2}]}
    after = {"log": [{"turn": 1}, {"turn": 2}, {"turn": 3}, {"turn": 4}]}
    delta = _round_trip(before, after)
    assert delta == [
        {"op": "add", "path": "/log/-", "value": {"turn": 3}},
        {"op": "add", "path": "/log/-", "value": {"turn": 4}},
    ]


def test_a_list_edited_in_place_or_trimmed_is_replaced() -> None:
    before = {"recent": [1, 2, 3], "window": [1, 2, 3]}
    after = {"recent": [1, 9, 3], "window": [2, 3, 4]}
    delta = _round_trip(before, after)
    assert {(op["op"], op["path"]) for op in delta} == {("replace", "/recent"), ("replace", "/window")}


def test_a_type_change_is_replaced_and_the_root_can_be_replaced() -> None:
    _round_trip({"flag": 1}, {"flag": "1"})
    _round_trip({"flag": {"a": 1}}, {"flag": [1]})
    assert state_delta([1], {"a": 1}) == [{"op": "replace", "path": "", "value": {"a": 1}}]
    assert apply_state_delta([1], state_delta([1], {"a": 1})) == {"a": 1}
