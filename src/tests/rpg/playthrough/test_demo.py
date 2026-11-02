"""Playthrough: the demo, a campaign already under way, is an opening of the starter world (RQ-2.8, roadmap §4.4)."""
from __future__ import annotations

from tests.rpg.playthrough.campaigns import POSTGRES, Playthrough
from tests.rpg.playthrough.scripted_model import Role

pytestmark = POSTGRES

PASS = "location:market-road:glimmerdeep-pass"


def test_the_demo_starts_mid_expedition_and_plays_on_in_its_world(model) -> None:
    from app.apps.rpg.session.new_game import list_rpg_presets, start_rpg_preset

    [preset] = list_rpg_presets()["presets"]
    assert (preset["preset_id"], preset["level"], preset["location"]) == ("demo_glimmerdeep_pass_lvl14", 14,
                                                                         "Glimmerdeep Pass")
    play = Playthrough(str(start_rpg_preset(preset["preset_id"])["session_id"]))
    play.model = model
    sheet = play.public()
    assert sheet["player"]["level"] == 14 and play.player_state()["level"] == 14
    assert sheet["player"]["currency"] == {"gold": 1248, "silver": 0, "copper": 0}
    assert {slot["name"] for slot in sheet["player"]["equipment"]} >= {"Longbow of the Boreal Wind", "Cloak of the Owl"}
    assert play.inventory()["Health Potion"] == 12 and play.inventory()["Longbow of the Boreal Wind"] == 1
    assert play.party() == ["npc:thorin", "npc:elandra", "npc:kael"]
    assert {title: quest["status"] for title, quest in play.quests().items()} == {
        "The Frostbound Relic": "active", "Secrets in the Snow": "active", "Bounty: Icefang Alpha": "active"}
    assert play.turn_count() == 73 and play.location() == PASS

    model.answer(Role.DIALOGUE, ("Thorin Ironfist", "Icefang. Big one."))
    body = play.turn("I ask Thorin about the tracks.")
    assert "Icefang. Big one." in body["visible_response"]["plain_text"]
    play.turn("go to the Glimmerdeep")
    assert play.location() == "location:market-road:the-glimmerdeep"
    assert play.party() == ["npc:thorin", "npc:elandra", "npc:kael"]  # the party travels with the hero
