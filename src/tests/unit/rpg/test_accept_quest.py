"""Taking on a quest (rules/player/requests.py): one offered is taken; one no one offered is refused by name."""
from __future__ import annotations

from app.apps.rpg.rules.player.requests import accept_quest

ROADS = {"quest_id": "quest:roads", "title": "Echo beasts on the March roads", "status": "available"}
SIMULATION = {"quest_state": {"quests": [ROADS]},
              "world_model": {"quests": {"quest:memory": {"title": "The Memory That Burned"}}}}


def test_the_one_offered_is_taken_when_none_is_named() -> None:
    taken = accept_quest(SIMULATION, "")
    assert not taken.refused and taken.changes[0].quest_id == "quest:roads"


def test_a_quest_no_one_offered_is_refused_and_never_another_taken_in_its_place() -> None:
    """The playtest: "I accept the quest The Memory That Burned", before Orik offered it, was a free action."""
    refused = accept_quest(SIMULATION, "quest:memory")
    assert refused.refused and refused.changes == [] and refused.lines == ["No one has offered you The Memory That Burned yet."]
