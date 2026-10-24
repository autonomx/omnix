"""Creatures act like themselves (RQ-5.6; docs/rpg/design/encounters.md): they flee when hurt, call allies, keep
their post, strike from ambush; and a creature the world says nothing of behaves as its lore tells."""
from __future__ import annotations

import pytest

from app.apps.rpg.foundation.state import reduce
from app.apps.rpg.foundation.state.changes import ExperienceGained
from app.apps.rpg.genesis.worlds.published_world_setup import derived_behaviour
from app.apps.rpg.rules.combat import fight as fight_rule
from app.apps.rpg.rules.combat.fight import fight
from tests.unit.rpg.test_fight import _document

# Each easy to hit and harmless, so the fight runs long enough for the creature to show what it is.
_BASE = {"level": 1, "defense": 1, "damage_min": 1, "damage_max": 1, "accuracy_bonus": -20, "xp_value": 40}
WOLF = {**_BASE, "definition_id": "creature:wolf", "name": "Wolf", "hp": 12, "initiative_bonus": 20,
        "behaviour": "flees_when_hurt"}
BRUTE = {**_BASE, "definition_id": "creature:brute", "name": "Brute", "hp": 12, "behaviour": "calls_allies"}
WARDEN = {**_BASE, "definition_id": "creature:warden", "name": "Warden", "hp": 400, "defense": 45,
          "initiative_bonus": 30, "behaviour": "guards"}
LURKER = {**_BASE, "definition_id": "creature:lurker", "name": "Lurker", "hp": 400, "defense": 45,
          "initiative_bonus": -30, "accuracy_bonus": 0, "behaviour": "ambushes"}


def _with(*creatures: dict) -> dict:
    document = _document()
    document["simulation_state"]["campaign_mechanics"] = {"creatures": {row["definition_id"]: row for row in creatures}}
    return document


def _play(document: dict, creature: str, *, limit: int = 40) -> tuple[dict, list]:
    turns = []
    for count in range(limit):
        turn = fight(document["simulation_state"], action="attack", target_ref=creature, turn_key=str(count))
        document, _ = reduce(document, turn.changes)
        turns.append(turn)
        if turn.ended:
            return document, turns
    raise AssertionError("the fight did not end")


def test_a_creature_that_flees_when_hurt_gets_away_and_the_fight_yields_nothing() -> None:
    document, turns = _play(_with(WOLF), "wolf")
    assert turns[-1].ended == "foe_fled"
    assert document["simulation_state"]["combat_state"]["ended_reason"] == "enemy_fled"
    assert not any(isinstance(change, ExperienceGained) for turn in turns for change in turn.changes)
    lines = [line for turn in turns for line in turn.lines]
    assert "The Wolf breaks away and flees." in lines and lines[-1] == "The fight is over; it yields you nothing."


def test_a_creature_that_calls_allies_does_once_and_its_ally_joins(monkeypatch) -> None:
    monkeypatch.setattr(fight_rule, "CALL_CHANCE", 100)  # answered, for the test (the chance is seeded, even)
    document, turns = _play(_with(BRUTE), "brute")
    joined = [line for turn in turns for line in turn.lines if "calls for help" in line]
    assert joined == ["The Brute calls for help, and the Brute joins the fight."]  # once, not by the ally too
    participants = document["simulation_state"]["combat_state"]["participants"]
    assert sorted(actor for actor in participants if actor.startswith("enemy:")) == ["enemy:creature-brute:1", "enemy:creature-brute:2"]
    assert turns[-1].ended == "victory"
    assert ExperienceGained(amount=80) in turns[-1].changes  # both fell: both pay


def test_from_a_guardian_the_hero_walks_away_unpursued() -> None:
    document = _with(WARDEN)
    started = fight(document["simulation_state"], action="attack", target_ref="warden", turn_key="0")
    document, _ = reduce(document, started.changes)
    fled = fight(document["simulation_state"], action="flee", turn_key="1")
    assert fled.ended == "fled" and fled.report["parting_blows"] == []


def test_an_ambusher_strikes_first() -> None:
    started = fight(_with(LURKER)["simulation_state"], action="attack", target_ref="lurker", turn_key="0")
    order = started.report["combat_state"]["initiative_order"]
    assert order[0]["actor_id"] == "enemy:creature-lurker:1" == started.report["earlier_turns"][0]["actor_id"]


@pytest.mark.parametrize(("name", "traits", "behaviour"), [
    ("Echo Wolf", ["mimics voices"], "flees_when_hurt"), ("Glass Wight", ["wears a stolen face"], "ambushes"),
    ("Rootbound Knight", ["obeys ancient oaths"], "guards"), ("Sky Manta", ["docile unless nesting"], "flees_when_hurt"),
    ("Hollow Archon", ["splits into conflicting versions"], "calls_allies"), ("Giant Rat", ["filthy"], "fights")])
def test_a_creature_the_world_says_nothing_of_behaves_as_its_lore_tells(name, traits, behaviour) -> None:
    assert derived_behaviour({"name": name, "traits": traits}) == behaviour
