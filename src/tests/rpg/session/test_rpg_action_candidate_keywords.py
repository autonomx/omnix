"""Turn keywords match whole words: "useful" does not use an item, nor "current" rent a room."""
from __future__ import annotations

import pytest

from app.apps.rpg.session.session_runtime_store import derive_action_candidates


def _types(text: str) -> set[str]:
    return {candidate["action_type"] for candidate in derive_action_candidates({}, text)}


@pytest.mark.parametrize(
    ("text", "absent"),
    [
        ("Search the area for useful supplies", "use_item"),
        ("I wait because the house is quiet", "use_item"),
        ("What a great view of the white cliffs", "use_item"),
        ("What a great view of the white cliffs", "attack_melee"),
        ("Ask about the current news and the different roads", "rent_room"),
        ("We sit by the fireplace during dinner", "attack_ranged"),
        ("We sit by the fireplace during dinner", "rent_room"),
    ],
)
def test_words_inside_other_words_do_not_trigger_actions(text: str, absent: str) -> None:
    assert absent not in _types(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("I use the healing potion", "use_item"),
        ("I eat my bread", "use_item"),
        ("I attack the wolf", "attack_melee"),
        ("Attacking the bandit now", "attack_melee"),
        ("I'd like to rent a room for the night", "rent_room"),
        ("I search the ruins", "investigate"),
    ],
)
def test_whole_words_still_trigger_actions(text: str, expected: str) -> None:
    assert expected in _types(text)
