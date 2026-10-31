"""Playthrough: consequences (evolution roadmap EV-1). A decision leaves facts behind, and the following turns show
them: a group's standing and how its people greet the hero, a seller's prices, a place, the journal's "What has
changed"."""
from __future__ import annotations

import pytest

from tests.rpg.playthrough.campaigns import POSTGRES

pytestmark = POSTGRES

ENGINE = "The Princess and the Engine"


def _to_the_engine_decision(play) -> None:
    """Seraphine spends the day at the Wayfarers' Guild; her engine's warden, Cassia, is in Valecourt."""
    play.turn("go to Starfall Village")
    play.turn("go to Wayfarers' Guild")
    assert "npc:seraphine-valecourt" in play.present()
    play.turn("Princess Seraphine, do you have any work for an Earthborn?")
    if play.quests().get(ENGINE, {}).get("status") != "active":
        play.turn(f"I accept the quest {ENGINE}.")
    if (play.quests()[ENGINE].get("progress") or {}).get("stage", 0) < 1:
        play.turn("Princess Seraphine, what help do you need with the engine?")
    assert play.quests()[ENGINE]["progress"]["stage"] == 1, play.quests()[ENGINE]
    play.turn("go to Starfall Village")
    play.turn("go to Valecourt")
    play.turn("Cassia Venn, show me the engine hall and its core.")
    assert play.quests()[ENGINE]["progress"]["stage"] == 2, play.quests()[ENGINE]
    play.turn("go to Starfall Village")
    play.turn("go to Wayfarers' Guild")
    assert "npc:seraphine-valecourt" in play.present()


def _hollis_price(play) -> int:
    from app.apps.rpg.rules.economy.trade import price_of

    simulation = play.simulation()
    world = simulation["world_model"]
    provider = world["providers"]["npc:hollis-brask"]
    offer = world["offers"]["npc:hollis-brask"][0]
    return price_of(simulation, provider, offer)[0]


@pytest.mark.parametrize("way, standing, price_moves, line", [
    ("mend it as it was", 30, -10, "The engine hall hums again"),
    ("the engine should belong to a council of the guilds and the people", -10, 0, "A council of guild masters"),
])
def test_the_engine_decision_changes_three_things_the_player_sees(launch, way, standing, price_moves, line) -> None:
    play = launch("aurelia")
    _to_the_engine_decision(play)
    before = _hollis_price(play)

    play.turn(f"Princess Seraphine, {way}.")
    simulation = play.simulation()
    assert play.quests()[ENGINE]["status"] == "completed"
    fate = simulation["world_facts"]["engine_fate"]
    assert fate["known"] is True and fate["told"] in play.public()["what_has_changed"]  # 1: the journal says so
    assert simulation["group_standing"]["faction:meridian-crown"] == standing  # 2: the crown's regard
    shown = {row["group_id"]: row for row in play.public()["group_standing"]}["faction:meridian-crown"]
    assert shown["name"] == "The Meridian Crown" and shown["standing"] == standing  # in words, by band
    play.turn("go to Starfall Village")
    play.turn("go to Valecourt")
    play.turn("look around")  # 3: the place itself
    assert line in play.model.told()
    after = _hollis_price(play)
    assert abs(after - before * (1 + price_moves / 100)) <= 1  # 4: the smith's prices


def test_orik_gives_a_new_arrival_one_night_free(launch) -> None:
    play = launch("aurelia")
    play.turn("go to Starfall Village")
    purse = play.purse()
    play.turn("I rent a room for the night from Orik.")
    assert play.purse() == purse  # the first night is on the house
    play.turn("I rent a room for the night from Orik.")
    assert play.purse() < purse  # the second is not
