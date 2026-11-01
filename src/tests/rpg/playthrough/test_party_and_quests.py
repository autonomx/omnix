"""Playthrough: companions and quests (RQ-0.3)."""
from __future__ import annotations

import pytest

from tests.rpg.playthrough.campaigns import POSTGRES, copper, in_worlds

pytestmark = POSTGRES

COMPANION = {"aurelia": ("Liora Fen", "npc:liora-fen", "go to Starfall Village"),
             "starter": ("Mira", "npc:mira", "go outside"),
             "vesper": ("Ines Okoro", "ent:actors:ines-okoro", "go to Tidebreak Docks")}


@pytest.mark.parametrize("world", in_worlds())
def test_companion_joins_and_follows(launch, world) -> None:
    play = launch(world)
    name, npc_id, travel = COMPANION[world]
    needs = play.survival()
    play.turn(f"I ask {name} to join my party as a companion.")
    assert play.party() == [npc_id]
    assert play.turn_count() == 1
    assert play.survival()["hunger"] > (needs.get("hunger") or 0)  # the joining turn passes time too
    play.turn(travel)
    assert npc_id in play.present()  # a companion goes where the hero goes
    assert play.party() == [npc_id]


@pytest.mark.parametrize("world", in_worlds("aurelia"))
def test_companion_takes_a_command_and_leaves(launch, world) -> None:
    play = launch(world)
    play.turn("I ask Liora Fen to join my party as a companion.")
    play.turn("Liora, keep watch while I rest.")
    companion = (play.player_state().get("party_state") or {}).get("companions")[0]
    assert companion.get("orders") or companion.get("command") or companion.get("stance") == "watch", companion
    play.turn("I tell Liora Fen to leave the party.")
    assert play.party() == []
    assert play.location() == "location:aurelia:arrival-grove"


@pytest.mark.parametrize("world", in_worlds("aurelia"))
def test_quest_from_offer_to_reward(launch, world) -> None:
    play = launch(world)
    quests = play.quests()
    assert quests["Voices in the Phone"]["status"] == "available"  # offered by the opening
    assert quests["First Night in Aurelia"]["status"] == "active"

    play.turn("I accept the quest Voices in the Phone.")
    assert play.quests()["Voices in the Phone"]["status"] == "active"
    assert "You take on the quest Voices in the Phone" in play.model.told()

    purse = play.purse()
    play.turn("go to Starfall Village")  # Aurelia's first night, step by step: the village, the guild, a companion
    first_night = play.quests()["First Night in Aurelia"]
    assert first_night["status"] == "active" and first_night["progress"]["stage"] == 1
    assert ("First Night in Aurelia: Reach Starfall Village. Next: Register with Miri Kestrel at the Wayfarers' Guild."
            in play.model.told())

    play.turn("go to Wayfarers' Guild")
    play.turn("I ask Miri Kestrel to register me with the guild.")
    assert play.quests()["First Night in Aurelia"]["objective"] == "Choose a first companion"
    play.turn("I ask Miri Kestrel to join my party.")
    assert play.quests()["First Night in Aurelia"]["status"] == "completed"
    assert play.purse() == purse + 200  # 20 silver
    assert play.inventory()["Wayfarer Sigil"] == 1
    assert "Quest complete: First Night in Aurelia. You receive 20 silver, Wayfarer Sigil." in play.model.told()
    shown = play.public()["player"]["currency"]
    assert copper(shown) == play.purse() and int(shown.get("silver") or 0) < 10  # coin carries into gold

    play.turn("look around")
    assert play.quests()["First Night in Aurelia"]["status"] == "completed"  # and stays completed
    assert play.purse() == purse + 200


@pytest.mark.parametrize("world", in_worlds("aurelia"))
def test_an_npc_offers_a_quest_in_conversation(launch, world) -> None:
    play = launch(world)
    play.turn("go to Starfall Village")
    play.turn("go to Wayfarers' Guild")
    before = {title: quest.get("offered_by") for title, quest in play.quests().items()}
    body = play.turn("I ask Miri Kestrel if she has any work for me.")
    # An offer names who made it; the quest waits, available, for the hero to take it (quests.md).
    after = {title: quest.get("offered_by") for title, quest in play.quests().items()}
    offered = [title for title, offerer in after.items() if offerer and offerer != before.get(title)]
    assert offered, after
    # The outcome card says so, whatever the line (the model may phrase the offer as it likes), and a card takes it.
    facts = [fact["text"] for fact in body["outcome"]["presentation"]["facts"]]
    assert f"Offered: {offered[0]}" in facts, facts
