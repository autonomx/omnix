"""Playthrough: companions and quests (RQ-0.3)."""
from __future__ import annotations

import pytest

from tests.rpg.playthrough.campaigns import POSTGRES, copper, in_worlds

pytestmark = POSTGRES

NO_WORLD_MODEL = ("RQ-2.0: a lore-only world (Vesper-9) launches with an empty world model: no one is present at "
                  "its opening to ask")
COMPANION = {"aurelia": ("Liora Fen", "npc:liora-fen", "go to Starfall Village"),
             "starter": ("Mira", "npc:Mira", "go outside"),
             "vesper": ("Ines Vale", "npc:ines-vale", "go to Tidebreak Docks")}


@pytest.mark.parametrize("world", in_worlds(vesper=NO_WORLD_MODEL, starter=(
    "RQ-2.5: the starter town's companions are not present in its tavern scene, so asking Mira to join adds "
    "no one")))
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


@pytest.mark.parametrize("world", in_worlds("aurelia", aurelia=(
    "RQ-2.5: a companion takes no command ('Liora, keep watch') and cannot be asked to leave: the command is "
    "an intent-model question and 'leave the party' is read as travel")))
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
    play.turn("go to Starfall Village")
    first_night = play.quests()["First Night in Aurelia"]
    assert first_night["status"] == "active" and "location:aurelia:starfall-village" in first_night["visited_locations"]
    assert "Progress on First Night in Aurelia: 2 of 3 places reached." in play.model.told()

    play.turn("go to Wayfarers' Guild")
    assert play.quests()["First Night in Aurelia"]["status"] == "completed"
    assert play.purse() == purse + 200  # 20 silver
    assert play.inventory()["Wayfarer Sigil"] == 1
    assert "Quest complete: First Night in Aurelia. You receive 20 silver, Wayfarer Sigil." in play.model.told()
    shown = play.public()["player"]["currency"]
    assert copper(shown) == play.purse() and int(shown.get("silver") or 0) < 10  # coin carries into gold

    play.turn("look around")
    assert play.quests()["First Night in Aurelia"]["status"] == "completed"  # and stays completed
    assert play.purse() == purse + 200


@pytest.mark.parametrize("world", in_worlds("aurelia", aurelia=(
    "RQ-2.2: no one offers a quest in conversation: asking Miri Kestrel for work is a line of dialogue, and no "
    "quest becomes offered (there is no DialoguePlan or QuestOffered change)")))
def test_an_npc_offers_a_quest_in_conversation(launch, world) -> None:
    play = launch(world)
    play.turn("go to Starfall Village")
    play.turn("go to Wayfarers' Guild")
    before = {title: quest["status"] for title, quest in play.quests().items()}
    play.turn("I ask Miri Kestrel if she has any work for me.")
    after = {title: quest["status"] for title, quest in play.quests().items()}
    offered = [title for title in after if before.get(title) != after[title] or title not in before]
    assert offered, after
    assert "offer" in play.model.told().lower()
