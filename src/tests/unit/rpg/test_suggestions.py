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
                                "Look around", "Rest", "Wait", "Status"]  # and the cards always on offer (EV-9)
    assert offered[2].command == "I accept the quest Rats."
    # Each is a card: the reading it plays, with no model call (EV-9).
    assert [row.action for row in offered[:4]] == [
        {"family": "talk", "target_id": "npc:orik"}, {"family": "talk", "target_id": "npc:liora"},
        {"family": "quest", "target_id": "q"}, {"family": "buy", "second_target_id": "npc:orik"}]
    assert offered[6].action == {"family": "rest", "slots": {"rest": "while"}}
    party = _document(player_state={"location_id": "loc:inn", "party_state": {"companions": [{"npc_id": "npc:liora"}]}})
    assert "Talk to Liora" not in _labels(suggestions(party))  # a companion is with the hero, not someone to meet


def test_in_a_fight_its_moves_and_before_blows_the_ways_out_of_it() -> None:
    combat = {"active": True, "combat_log": [], "participants": {
        "player": {"side": "party", "hp": 10}, "enemy:1": {"side": "enemy", "name": "Bandit", "hp": 5, "speaks": True}}}
    offered = suggestions(_document(combat_state=combat))
    assert _labels(offered) == ["Attack the Bandit", "Defend", "Break away", "Slip past", "Talk it down", "Status"]
    assert [row.action.get("check") for row in offered[3:5]] == ["sneak", "persuade"]
    struck = {**combat, "combat_log": [{"kind": "attack"}]}
    assert _labels(suggestions(_document(combat_state=struck))) == ["Attack the Bandit", "Defend", "Break away", "Status"]


def test_a_question_comes_with_its_answers() -> None:
    assert [(row.label, row.command) for row in choices(_document(), "move_without_place")] == [
        ("The Road", "go to The Road")]
    assert _labels(choices(_document(), "speech_without_listener")) == ["Orik", "Liora"]
    assert _labels(choices(_document(), "attack_without_target")) == ["Orik", "Liora"]
    assert choices(_document(), "give_without_item") == []


def test_a_waiting_level_choice_is_offered_first_and_said_by_status() -> None:
    """The playtest: level 2 was reached, a choice waited, and nothing on the screen said so."""
    from app.apps.rpg.rules.player.requests import status
    from app.apps.rpg.session.turn.suggestions import suggestions

    simulation = {"player_state": {"level": 2, "xp": 80, "xp_to_next": 200, "level_choices_pending": 1,
                                   "skills": {"stealth": {"level": 1, "xp": 5}, "persuasion": {"level": 0, "xp": 20},
                                              "archery": {"level": 0, "xp": 0}}}}
    offered = suggestions({"simulation_state": simulation})
    assert [row.command for row in offered[:2]] == ["raise strength", "improve stealth and persuasion"]
    told = status(simulation, ("progress",)).lines
    assert any("A level's choice is waiting" in line for line in told)
    simulation["player_state"]["level_choices_pending"] = 0
    assert not any(row.command == "raise strength" for row in suggestions({"simulation_state": simulation}))


def test_the_quest_suggested_is_one_someone_offered_and_a_finale_last() -> None:
    """The playtest: "I accept the quest The Hollow Meridian." was suggested on every screen, never the captain's
    contract just offered."""
    from app.apps.rpg.session.turn.suggestions import suggestions

    simulation = {"quest_state": {"quests": [
        {"quest_id": "quest:finale", "title": "The Hollow Meridian", "status": "available", "tier": "finale"},
        {"quest_id": "quest:wolves", "title": "Echo beasts on the March roads", "status": "available",
         "offered_by": "npc:rhea"}]}}
    commands = [row.command for row in suggestions({"simulation_state": simulation})]
    assert "I accept the quest Echo beasts on the March roads." in commands
    assert "I accept the quest The Hollow Meridian." not in commands


def test_what_the_heros_quests_ask_now_comes_first() -> None:
    """The playtest: at the Hollow Meridian the Archon's fight was not offered, nor the road to Valecourt."""
    def quest(step: dict, places: list[str]) -> dict:
        return {"quest_id": "q:main", "title": "Main", "status": "active", "locations": places,
                "progress": {"stage": 0}, "steps": [{"id": "s", "summary": "Do it", "all_of": [step]}]}

    archon = _document(quest_state={"quests": [quest({"defeat": "creature:archon"}, ["loc:inn"])]},
                       campaign_mechanics={"creatures": {"creature:archon": {"name": "Hollow Archon"}}})
    first = suggestions(archon)[0]
    assert (first.label, first.command) == ("Fight the Hollow Archon", "I attack the Hollow Archon.")
    far = suggestions(_document(quest_state={"quests": [quest({"reach": "loc:far"}, [])]}))
    assert _labels(far)[0] == "Go to Far"  # set out for it: the journey goes by its roads
    orik = suggestions(_document(quest_state={"quests": [quest({"talk": "npc:orik"}, [])]}))
    assert _labels(orik)[:2] == ["Talk to Orik", "Talk to Liora"]  # once, first
