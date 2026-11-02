"""Playthrough: the game master (evolution roadmap EV-0, part 1). Its panel answers from what the hero knows and
changes nothing; an answer that would tell a secret is withheld; a wish it offers is a card the player confirms; and
its direction, after a scene ends, reaches the campaign only through the proposal record, folded into the next turn."""
from __future__ import annotations

from tests.rpg.playthrough.campaigns import POSTGRES
from tests.rpg.playthrough.scripted_model import Role

pytestmark = POSTGRES


def _ask(play, question: str) -> dict:
    response = play.client.post(f"/api/rpg/sessions/{play.session_id}/game-master", json={"question": question})
    assert response.status_code == 200, response.text[:300]
    return response.json()["entry"]


def test_a_question_to_the_game_master_changes_nothing_and_is_logged(launch) -> None:
    play = launch("aurelia")
    play.turn("look around")
    revision, facts = play.revision(), play.facts()
    play.model.answer(Role.GAME_MASTER, {"answer": "You stand in Starfall Grove. The village lies along the path.",
                                         "wish": None})
    entry = _ask(play, "Where am I, and what could I do next?")
    assert entry["answer"].startswith("You stand in Starfall Grove") and entry["withheld"] is False
    assert play.revision() == revision and play.facts() == facts  # no turn, no change
    logged = play.client.get(f"/api/rpg/sessions/{play.session_id}/game-master").json()["entries"]
    assert logged[0]["question"] == "Where am I, and what could I do next?"
    calls = [call for call in play.model.calls if call.role is Role.GAME_MASTER]
    assert calls and "secrets" not in calls[-1].text  # its prompt holds what the hero knows, and no secret field


def test_an_answer_that_would_tell_a_secret_is_withheld(launch) -> None:
    play = launch("aurelia")
    secret = play.simulation()["world_model"]["npcs"]["npc:liora-fen"]["secrets"][0]
    play.model.answer(Role.GAME_MASTER, {"answer": f"Here is a truth: {secret}.", "wish": None})
    entry = _ask(play, "What is Liora hiding?")
    assert entry["withheld"] is True and secret not in entry["answer"]


def test_a_wish_offered_is_a_card_the_player_confirms(launch) -> None:
    play = launch("aurelia")
    play.model.answer(Role.GAME_MASTER, {"answer": "Then the road will bite harder.",
                                         "wish": {"kind": "danger", "value": "more"}})
    entry = _ask(play, "I want more danger.")
    assert entry["wish"] == {"kind": "danger", "value": "more"}
    response = play.client.post(f"/api/rpg/sessions/{play.session_id}/turn",
                                json={"command": "Note: more danger.", "preference": entry["wish"]})
    assert response.status_code == 200, response.text[:300]
    assert play.simulation()["direction"]["wishes"] == [{"kind": "danger", "value": "more"}]


def test_the_game_masters_direction_reaches_the_campaign_only_through_the_next_turn(launch) -> None:
    from app.apps.rpg.narration.game_master.direction_call import direct, trigger

    play = launch("aurelia")
    arrived = play.turn("go to Starfall Village")
    stored = play.stored()
    assert trigger({"turn_pipeline": {"changes": [{"type": "location_changed"}]}}, stored)
    play.model.answer(Role.GAME_MASTER, {"proposals": [
        {"kind": "gm_fact", "payload": {"fact": "festival_tonight", "value": True,
                                        "told": "Lanterns are strung for a festival tonight."},
         "reason": "the village should feel alive"},
        {"kind": "gm_move_person", "payload": {"npc_id": "npc:no-one", "location_id": "x"}, "reason": "?"}]})
    report = direct(play.session_id, stored, "the hero arrived", revision=play.revision())
    assert report["proposed"] == 1 and report["dropped"] == ["gm_move_person: no such npc"]
    assert "festival_tonight" not in play.simulation().get("world_facts", {})  # not yet: a proposal
    play.turn("look around")
    facts = play.simulation()["world_facts"]
    assert facts["festival_tonight"]["source"] == "game_master"
    assert "Lanterns are strung for a festival tonight." in play.public()["what_has_changed"]
    assert arrived  # the arrival's own turn made no direction call: it is a job after the commit
