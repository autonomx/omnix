"""What the play screen offers next (RQ-7.3; session/turn/suggestions.py)."""
from __future__ import annotations

from app.apps.rpg.session.turn.suggestions import choices, suggestions


def _document(**simulation) -> dict:
    base = {
        "player_state": {"location_id": "loc:inn"},
        "present_npc_state": {"location_id": "loc:inn", "present_npc_ids": ["npc:orik", "npc:liora"]},
        "world_model": {
            "npcs": {"npc:orik": {"name": "Orik"}, "npc:liora": {"name": "Liora"}},
            "locations": {"loc:inn": {"name": "The Inn"}, "loc:road": {"name": "The Road"}, "loc:far": {"name": "Far"}},
            "routes": [{"from": "loc:inn", "to": "loc:road"}, {"from": "loc:road", "to": "loc:far"}],
            "offers": {"npc:orik": [{"label": "Stew"}]},
        },
        "quest_state": {"quests": [{"quest_id": "q", "title": "Rats", "status": "available"}]},
    }
    return {"simulation_state": {**base, **simulation}}


def _labels(rows) -> list[str]:
    return [row.label for row in rows]


def test_outside_a_fight_the_people_here_a_quest_a_sellers_wares_the_roads_and_a_look() -> None:
    offered = suggestions(_document())
    assert _labels(offered) == ["Talk to Orik", "Talk to Liora", "Take on Rats", "See Orik's wares", "Go to The Road",
                                "Look around"]
    assert offered[2].command == "I accept the quest Rats."
    party = _document(player_state={"location_id": "loc:inn", "party_state": {"companions": [{"npc_id": "npc:liora"}]}})
    assert "Talk to Liora" not in _labels(suggestions(party))  # a companion is with the hero, not someone to meet


def test_in_a_fight_its_moves_and_before_blows_the_ways_out_of_it() -> None:
    combat = {"active": True, "combat_log": [], "participants": {
        "player": {"side": "party", "hp": 10}, "enemy:1": {"side": "enemy", "name": "Bandit", "hp": 5, "speaks": True}}}
    assert _labels(suggestions(_document(combat_state=combat))) == [
        "Attack the Bandit", "Defend", "Break away", "Slip past", "Talk it down"]
    struck = {**combat, "combat_log": [{"kind": "attack"}]}
    assert _labels(suggestions(_document(combat_state=struck))) == ["Attack the Bandit", "Defend", "Break away"]


def test_a_question_comes_with_its_answers() -> None:
    assert [(row.label, row.command) for row in choices(_document(), "move_without_place")] == [
        ("The Road", "go to The Road")]
    assert _labels(choices(_document(), "speech_without_listener")) == ["Orik", "Liora"]
    assert _labels(choices(_document(), "attack_without_target")) == ["Orik", "Liora"]
    assert choices(_document(), "give_without_item") == []
