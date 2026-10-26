"""Playthrough: each bug fixed in the RPG since 2026-10-20, played again in Aurelia (RQ-0.3).

Every scenario names the commit that fixed it. They play through the production routes with the scripted
model, so a bug that comes back fails here before it reaches live play.
"""
from __future__ import annotations

import json

import pytest

from tests.rpg.playthrough.campaigns import POSTGRES, copper
from tests.rpg.playthrough.scripted_model import Role

pytestmark = POSTGRES

STARTER_NAMES = ("Rusty Flagon", "loc_tavern", "Bran the Innkeeper", "Captain Aldric", "Elara the Merchant")


@pytest.fixture
def play(launch):
    return launch("aurelia")


def test_a_published_campaign_plays_in_its_own_world(play) -> None:
    """12248857f2: the opening's place, region, kit, purse and quests; never the starter town."""
    opening = play.public()
    assert opening["current_location_name"] == "Starfall Grove"
    assert opening["environment_snapshot"]["display"]["region"] == "Starfall March"
    assert play.inventory() == {"Gateborn Compass": 1, "Iron Dagger": 1, "Lantern Bread": 2, "Travel Cloak": 1}
    assert opening["player"]["currency"] == {"gold": 0, "silver": 12, "copper": 40}
    play.turn("look around")
    play.turn("go to Starfall Village")
    text = json.dumps(play.stored())
    for starter in STARTER_NAMES:
        assert starter not in text, starter


def test_item_actions_and_story_turns_keep_one_inventory(play) -> None:
    """e9927c7be2: a loadout action is kept by the next story turn, stacks keep their count, and whole words
    decide ("useful" is not "use", "current" rents nothing, "white" attacks no one)."""
    play.turn("look around")
    assert play.inventory()["Lantern Bread"] == 2  # a stack of two stays two after the first turn
    assert play.loadout("drop", "Lantern Bread").status_code == 200
    play.turn("look around")
    assert play.inventory()["Lantern Bread"] == 1
    purse = play.purse()
    play.turn("Search the area for useful supplies I can pick up")
    play.turn("I study the current of the white river.")
    assert play.inventory()["Lantern Bread"] == 1 and play.purse() == purse
    assert not play.combat().get("active")


def test_mechanics_change_real_state_and_survival_reads_whole_words(play) -> None:
    """973de8c471: joining, quests and practice change state; needs rise every turn and "forest" is not
    "rest"; asking for your quests reports them from state."""
    play.turn("wait")
    tired = play.survival()["fatigue"]
    play.turn("I walk along the forest edge and look at the trees.")
    assert play.survival()["fatigue"] > tired
    calls = len(play.model.calls)
    shown = play.turn("Check my quests")["visible_response"]["plain_text"]
    assert "Active quests: First Night in Aurelia" in shown
    assert "Quests you could take on: Voices in the Phone, The Hollow Meridian" in shown
    assert play.model.roles(calls) == []  # the game reads it off the campaign; no model rephrases it (RQ-2.5)


def test_every_turn_counts_and_the_narrator_is_told_the_purchase(play) -> None:
    """b1ad3bbff0: a companion's acceptance and a service purchase are counted; the narrator is told the
    purchase and what it eases."""
    play.turn("I ask Liora Fen to join my party as a companion.")
    play.turn("go to Starfall Village")
    play.turn("I buy a meal from Orik Stonewake.")
    assert play.turn_count() == 3 and play.stored()["manifest"]["turn_count"] == 3
    # Aurelia's roads choke its trade from the start: its prices carry the roads' fifth (economy.md).
    assert ("You pay 1 silver to Orik Stonewake for A hot meal (the roads choke trade). The transaction is complete. "
            "It eases your hunger.") in play.model.told()


def test_commands_the_game_resolves_itself_ask_no_model(play) -> None:
    """bb83af47aa: services, joining, quests, practice, status, travel to a named place, waiting and looking
    make no intent call; meeting the world's own people writes no dossier."""
    for command in ("look around", "I ask Liora Fen to join my party as a companion.", "I accept the quest Voices "
                    "in the Phone.", "Practice swordsmanship with a careful training drill.", "Check my quests",
                    "go to Starfall Village", "wait", "I buy a meal from Orik Stonewake."):
        calls = len(play.model.calls)
        play.turn(command)
        assert Role.INTENT.value not in play.model.roles(calls), command
    assert Role.LORE.value not in play.model.roles(), play.model.roles()


def test_an_arrival_is_described_once(play) -> None:
    """28468fce18 and 8a79930f8f: arriving, the narrator is told the place from the world's own description,
    and the arrival is told once (no second beat repeating it)."""
    body = play.turn("go to Starfall Village")
    village = play.simulation()["world_model"]["locations"]["location:aurelia:starfall-village"]
    assert village["description"] and village["description"] in play.model.told()
    texts = [block["text"] for block in body["canonical_narrative_response"]["blocks"]]
    arrival = [text for text in texts if village["description"] in text]
    assert len(arrival) == 1, texts


def test_a_question_to_someone_present_is_answered_by_them(play) -> None:
    """528803d8c3: one short call writes their line; the authored person is not met as a newcomer."""
    play.model.answer(Role.DIALOGUE, ("Liora Fen", "You stand in Starfall Grove, Earthborn."))
    calls = len(play.model.calls)
    body = play.turn("I greet Liora Fen and ask her where I am")
    assert play.model.roles(calls) == ["dialogue"]
    assert body["visible_response"]["messages"][0]["speaker_id"] == "npc:liora-fen"
    assert body["visible_response"]["messages"][0]["text"] == "You stand in Starfall Grove, Earthborn."


def test_trade_keeps_one_purse_and_sells_only_what_the_world_offers(play) -> None:
    """8a79930f8f: no starter merchant behind an unnamed purchase; "supplies" lists the offers and sells
    nothing; a shopkeeper buys back at half price, other goods for a token, and no quest reward."""
    purse = play.purse()
    play.turn("I buy a healing potion.")  # no one at the grove sells
    assert play.purse() == purse and "Healing Potion" not in play.inventory()
    play.turn("go to Starfall Village")
    play.turn("I buy supplies from Brindle Gearwing.")
    assert "Brindle Gearwing offers:" in play.model.told() and play.purse() == purse
    play.turn("I buy a Healing Potion from Brindle Gearwing.")
    play.turn("I sell my Healing Potion to Brindle Gearwing.")
    assert play.purse() == purse - 36 + 15  # bought at 30 and the roads' fifth, sold back at half the list price
    play.turn("I sell my Iron Dagger to Brindle Gearwing.")
    assert "You sell the Iron Dagger to Brindle Gearwing for 5 copper." in play.model.told()
    assert play.purse() == purse - 36 + 15 + 5
    play.turn("go to Wayfarers' Guild")  # First Night in Aurelia pays 20 silver and the Wayfarer Sigil
    play.turn("I ask Miri Kestrel to register me with the guild.")
    play.turn("I ask Miri Kestrel to join my party.")  # its last step: a first companion
    play.turn("go to Starfall Village")
    reward = play.purse()
    play.turn("I sell my Wayfarer Sigil to Brindle Gearwing.")
    assert play.purse() == reward and play.inventory()["Wayfarer Sigil"] == 1
    assert len(set(play.purses().values())) == 1, play.purses()
    shown = play.public()["player"]["currency"]
    assert copper(shown) == reward and int(shown["silver"]) < 10  # 20 silver carries into gold


def test_dropped_things_lie_where_they_fell_and_rejoin_their_stack(play) -> None:
    """8a79930f8f: drop and pick up resolve the item by name, and it lies where it was put down."""
    play.turn("I drop one Lantern Bread on the ground.")
    assert "You put down the Lantern Bread" in play.model.told()
    play.turn("go to Starfall Village")
    play.turn("I pick up the Lantern Bread.")
    assert play.inventory()["Lantern Bread"] == 1
    play.turn("go to Starfall Grove")
    play.turn("I pick up the Lantern Bread.")
    assert play.inventory()["Lantern Bread"] == 2


def test_a_worlds_creatures_fight_blow_by_blow_with_companions(play) -> None:
    """9457f8e162: the creature is found inside a longer phrase, creatures and companions take their turns,
    the narrator is told each blow by name, and the fight keeps the turn's time passing."""
    play.turn("I ask Liora Fen to join my party as a companion.")
    play.to_the_wild()  # with Liora along
    hunger = play.survival()["hunger"]
    play.turn("I attack the echo wolf with my dagger.")
    told = play.model.told()
    assert "The fight begins: you against the Echo Wolf." in told
    assert "Liora Fen misses the Echo Wolf" in told or "Liora Fen hits the Echo Wolf" in told, told
    assert play.survival()["hunger"] > hunger
    hero = play.combat()["participants"]["player"]
    assert play.hp() == hero["hp"]
    assert play.party() == ["npc:liora-fen"]
    assert (play.player_state()["party_state"]["companions"][0]["name"]) == "Liora Fen"


def test_renting_a_room_is_buying_one(play) -> None:
    """9457f8e162: "rent" and "book" are purchase words; a room eases fatigue when slept in, not when paid."""
    play.turn("go to Starfall Village")
    purse = play.purse()
    play.turn("I book a room for the night with Orik Stonewake.")
    assert play.purse() == purse - 60  # 5 silver, and the roads' fifth
    tired = play.survival()["fatigue"]
    assert tired > 0
    play.turn("I go to my room and sleep for the night.")
    assert play.survival()["fatigue"] < tired
    assert "rest" in play.model.told() and "lodging" in play.model.told()


def test_travel_follows_the_world_routes_by_name(play) -> None:
    """RQ-0.3 (fixed here): a route is named by where it leads, both ways, and a word two places share or the
    place the hero stands in sends no one anywhere ("go to Starfall Village" in the village used to lead back
    out to Starfall Grove; "go to Moonroot Ruins" from the village led to the Wayfarers' Guild). A place further
    off is set out for by the first road of its way (time.md)."""
    play.turn("go to Starfall Village")
    play.turn("go to Starfall Village")
    assert play.location() == "location:aurelia:starfall-village"
    play.turn("I ask Liora Fen to leave.")
    assert play.location() == "location:aurelia:starfall-village"
    play.turn("go to Moonroot Ruins")
    assert play.location() == "location:aurelia:skybridge-pass"  # on the way to the ruins, not the guild


def test_a_second_import_of_a_lore_world_prepares_its_openings(launch) -> None:
    """a78aa93de0: Vesper-9 imported twice (a clone under another world id) prepares and launches its openings
    both times; the second's scenario ids are qualified by its world."""
    first, second = launch("vesper"), launch("vesper")
    for play in (first, second):
        assert play.public()["current_location_name"] == "Black Rain Station"
        assert "Borrowed Night" in play.quests()
    assert first.stored()["manifest"]["scenario_id"] != second.stored()["manifest"]["scenario_id"]


def test_a_hero_of_a_world_to_come_sets_out_with_its_kind_of_gear_and_a_purse(launch) -> None:
    """The third playtest: a cyberpunk hero of Vesper-9 set out with a travel cloak, an iron dagger and no coin."""
    play = launch("vesper")
    carried = play.inventory()
    assert "Utility Knife" in carried and "Rain Cloak" in carried
    assert "Iron Dagger" not in carried and "Travel Cloak" not in carried
    assert play.purse() > 0  # the opening names no purse: the build's
    [opening] = [quest for quest in play.public()["quests"] if quest.get("source") == "published_opening_scenario"]
    assert opening["objective"]  # what it asks now (its quest showed none)
