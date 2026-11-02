"""The dialogue plan (RQ-2.2; docs/rpg/design/dialogue.md): rules decide what is said, the model phrases it."""
from __future__ import annotations

from typing import Any

import pytest

from app.apps.rpg.foundation.state.changes import DialogueExchanged, KnowledgeShared, QuestOffered
from app.apps.rpg.rules.dialogue.plan import line_keeps_the_plan, plan_changes
from tests.support.rpg_reading import answered, planned
from app.apps.rpg.session.turn import dialogue as turn_dialogue

ORIK = "npc:orik"


def _simulation(*, trust: int = 0, known: list[str] | None = None) -> dict[str, Any]:
    return {
        "present_npc_state": {"present_npc_ids": [ORIK]},
        "relationship_state": {ORIK: {"trust": trust}},
        "dialogue": {"known_facts": {ORIK: known or []}},
        "world_model": {
            "npcs": {ORIK: {
                "name": "Orik Stonewake", "role": "innkeeper", "location_id": "loc:inn",
                "speech_style": "gruff and brief", "personality": ["wary"], "goals": ["keep the inn"],
                "description": "Runs the Stonewake inn.", "secrets": ["He buried the smuggler's gold under the cellar"],
            }},
            "knowledge": [{"npc_id": ORIK, "facts": [
                {"fact_id": "fact:road", "text": "The east road floods after rain.", "topics": ["road"]},
                {"fact_id": "fact:tower", "text": "Lights burn in the old tower.", "topics": ["tower"],
                 "shares": "when_trusted", "trust_needed": 40},
                {"fact_id": "fact:map", "text": "A map of the caves exists.", "topics": ["caves"],
                 "shares": "for_price", "price": {"silver": 2}},
            ]}],
            "offers": {ORIK: [{"label": "Room", "price": {"silver": 3}}, {"label": "Stew", "price": {"copper": 5}}]},
        },
        "quest_state": {"quests": [
            {"quest_id": "quest:rats", "title": "Rats in the Cellar", "objective": "Clear the cellar",
             "status": "available", "locations": ["loc:inn"]},
        ]},
    }


def test_a_fact_asked_about_is_shared_once_and_made_known() -> None:
    plan = planned(_simulation(), ORIK, "What do you know about the road east?")
    assert plan is not None and plan.reveals == ("The east road floods after rain.",)
    assert plan_changes(plan) == [KnowledgeShared(npc_id=ORIK, fact_id="fact:road")]
    again = planned(_simulation(known=["fact:road"]), ORIK, "Tell me about the road again")
    assert again is not None and again.reveals and plan_changes(again) == []



def test_the_speakers_own_name_asks_about_none_of_what_they_know() -> None:
    simulation = _simulation()
    simulation["world_model"]["knowledge"][0]["facts"].append(
        {"fact_id": "fact:kettle", "text": "Orik's kettle predicts the rain.", "topics": ["kettle"]})
    plan = planned(simulation, ORIK, "I ask Orik Stonewake what the stew costs.")
    assert plan is not None and plan.reveals == ()
    asked = planned(simulation, ORIK, "Orik, what about your kettle?")
    assert asked is not None and asked.reveals == ("Orik's kettle predicts the rain.",)
    simulation["world_model"]["offers"][ORIK].append({"label": "Orik's Own Ale", "price": {"copper": 9}})
    priced = planned(simulation, ORIK, "I ask Orik what the stew costs.")
    assert priced is not None and priced.wares == ("Stew for 5 copper",)  # not his ale, for his name

def test_a_trusted_fact_waits_for_trust_and_a_priced_one_names_its_price() -> None:
    wary = planned(_simulation(trust=10), ORIK, "What about the tower and the caves?")
    assert wary is not None and wary.reveals == () and wary.held_back == 1
    assert wary.for_a_price == ("caves for 2 silver",)
    trusted = planned(_simulation(trust=60), ORIK, "What about the tower?")
    assert trusted is not None and trusted.reveals == ("Lights burn in the old tower.",)
    assert trusted.stance == "friendly"
    assert planned(_simulation(trust=-5), ORIK, "hello").stance == "wary"


def test_asked_for_work_they_offer_the_quest_where_they_stand() -> None:
    plan = planned(_simulation(), ORIK, "Got any work for me?")
    assert plan is not None and plan.quest_offer["quest_id"] == "quest:rats"
    assert QuestOffered(quest_id="quest:rats", npc_id=ORIK) in plan_changes(plan)
    assert plan.fallback_line() == "There is something you could do: Rats in the Cellar. Clear the cellar."


def test_asked_what_they_sell_they_list_their_wares_with_prices() -> None:
    plan = planned(_simulation(), ORIK, "What do you sell?")
    assert plan is not None and plan.wares == ("Room for 3 silver", "Stew for 5 copper")
    assert plan.fallback_line() == "I have Room for 3 silver, Stew for 5 copper."
    assert line_keeps_the_plan(plan, "A room is 3 silver, and the stew is 5 copper.")
    assert not line_keeps_the_plan(plan, "Welcome, traveler.")  # the prices are the game's: the plan lists them


def test_goods_sold_out_are_not_offered() -> None:
    simulation = _simulation()
    simulation["world_model"]["offers"][ORIK][1].update({"offer_id": f"{ORIK}:stew", "stock": 4})
    simulation["trade"] = {"stock": {f"{ORIK}:stew": 0}}
    plan = planned(simulation, ORIK, "What do you sell?")
    assert plan is not None and plan.wares == ("Room for 3 silver",)


def test_someone_the_world_does_not_know_has_no_plan() -> None:
    assert planned(_simulation(), "npc:nobody", "hello") is None


@pytest.mark.parametrize("line, keeps", [
    ("The road floods, mind you.", True),
    ("", False),
    ("I buried the smuggler's gold under the cellar, you know.", False),
    ("Gold? Buried under my cellar by a smuggler? Nonsense.", False),
])
def test_a_line_that_gives_away_a_secret_is_not_shown(line: str, keeps: bool) -> None:
    plan = planned(_simulation(), ORIK, "hello")
    assert plan is not None and line_keeps_the_plan(plan, line) is keeps


def _session(**kwargs: Any) -> dict[str, Any]:
    return {"simulation_state": _simulation(**kwargs), "runtime_state": {}}


def test_the_model_phrases_the_line_and_the_exchange_is_recorded(monkeypatch) -> None:
    monkeypatch.setattr(turn_dialogue, "_write_line", lambda plan, exchanges, text: "Orik Stonewake: \"It floods.\"")
    resolved = answered(_session(), ORIK, "Tell me about the road")
    assert resolved is not None and resolved.line == "It floods." and resolved.written_by_model
    assert resolved.changes[-1] == DialogueExchanged(npc_id=ORIK, name="Orik Stonewake",
                                                     player_line="Tell me about the road", npc_line="It floods.")
    assert KnowledgeShared(npc_id=ORIK, fact_id="fact:road") in resolved.changes


def test_a_secret_or_a_silent_model_falls_back_to_the_plans_own_line(monkeypatch) -> None:
    monkeypatch.setattr(turn_dialogue, "_write_line",
                        lambda plan, exchanges, text: "I buried the smuggler's gold under the cellar.")
    leaked = answered(_session(), ORIK, "Tell me about the road")
    assert leaked is not None and leaked.line == "The east road floods after rain." and not leaked.written_by_model
    monkeypatch.setattr(turn_dialogue, "_write_line", lambda plan, exchanges, text: "")
    silent = answered(_session(), ORIK, "Nice weather")
    assert silent is not None and silent.line == ""
    assert silent.lines[-1] == "Orik Stonewake considers the question and says nothing useful."
    assert not any(isinstance(change, DialogueExchanged) for change in silent.changes)
    for raw in ("{}", '{"line": "It floods."}', "<p>It floods.</p>", "...", "42"):  # no words said: no line
        monkeypatch.setattr(turn_dialogue, "_write_line", lambda plan, exchanges, text, raw=raw: raw)
        result = answered(_session(), ORIK, "Tell me about the road")
        assert result is not None and result.line == "The east road floods after rain.", raw
        assert not result.written_by_model


def test_only_someone_present_answers() -> None:
    session = _session()
    session["simulation_state"]["present_npc_state"]["present_npc_ids"] = []
    assert answered(session, ORIK, "hello") is None


def test_asked_about_one_ware_they_name_that_one() -> None:
    plan = planned(_simulation(), ORIK, "What does a room cost?")
    assert plan is not None and plan.wares == ("Room for 3 silver",)
    assert line_keeps_the_plan(plan, "A room is three silver a night.")


def test_their_goals_lead_what_they_say_and_which_quest_they_offer() -> None:
    """RQ-4.3: a person's goals (the world's routines author them) bias the plan: the goals the hero's words touch
    first, and the quest that answers what they are after."""
    simulation = _simulation()
    simulation["world_model"]["routines"] = [{"npc_id": ORIK, "schedule": [], "goals": [
        {"goal_id": "goal:debts", "summary": "Pay off the brewer", "priority": 1, "topics": ["brewer", "debt"]},
        {"goal_id": "goal:wolves", "summary": "Keep the wolves from the road", "priority": 3, "topics": ["wolves"]}]}]
    simulation["quest_state"]["quests"].append(
        {"quest_id": "quest:wolves", "title": "Wolves on the Road", "objective": "Drive off the wolves",
         "status": "available", "giver_id": ORIK})
    plan = planned(simulation, ORIK, "Good evening.")
    assert plan.goals[:2] == ("Keep the wolves from the road", "Pay off the brewer") and plan.goals[2] == "keep the inn"
    assert plan.quest_offer == {}  # neither work nor a goal of theirs asked about
    asked = planned(simulation, ORIK, "Any trouble with the wolves?")
    assert asked.quest_offer["quest_id"] == "quest:wolves"  # a goal of theirs, and a quest that answers it
    work = planned(simulation, ORIK, "Do you have any work for me?")
    assert work.quest_offer["quest_id"] == "quest:wolves"  # of the two, the one their most pressing goal is after
    owed = planned(simulation, ORIK, "How is the debt to the brewer?")
    assert owed.goals[0] == "Pay off the brewer" and owed.quest_offer == {}  # touched, but no quest answers it


def test_a_reply_written_beside_the_intent_call_is_used_only_for_the_plan_it_was_written_for(monkeypatch) -> None:
    """EV-9: in a conversation under way, the reply is written from the topic-free plan beside the intent call. It is
    used when the reading's topics add nothing to the plan; a line that asks of something they share is answered
    from its own plan, and the held reply is discarded (counted apart)."""
    written: list[tuple[str, bool]] = []

    def write(plan, exchanges, text, held=False):
        written.append((text, held))
        return "Held." if held else "Fresh."

    monkeypatch.setattr(turn_dialogue, "_write_line", write)
    session = {**_session(), "runtime_state": {"dialogue_focus": {"target_id": ORIK}}}
    assert turn_dialogue.under_way(session) == ORIK
    assert turn_dialogue.under_way(_session()) == ""  # no conversation: nothing is written ahead

    turn_dialogue.hold_reply(session, "Nice weather.")
    small_talk = turn_dialogue.resolve_dialogue(session, ORIK, "Nice weather.")
    assert small_talk.line == "Held." and turn_dialogue.settle_held_reply() == "used"
    assert written == [("Nice weather.", True)]  # one call: the held reply

    written.clear()
    held = turn_dialogue.hold_reply(session, "Tell me about the road")
    asked = turn_dialogue.resolve_dialogue(session, ORIK, "Tell me about the road", topics=("fact:road",))
    assert asked.line == "Fresh." and turn_dialogue.settle_held_reply() == "discarded"
    held.future.result(timeout=5)  # its call ran, beside the turn's
    assert sorted(written) == [("Tell me about the road", False), ("Tell me about the road", True)]
    assert turn_dialogue.settle_held_reply() == ""  # settled once
