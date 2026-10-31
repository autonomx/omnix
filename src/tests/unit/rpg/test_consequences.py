"""EV-1 (evolution roadmap 2026-10-29): facts a decision leaves, and what they change."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from app.apps.rpg.foundation.state import changes as c
from app.apps.rpg.foundation.state.reducer import reduce
from app.apps.rpg.genesis.worlds.world_play_sections import FactEffect, QuestPlay, quest_canon_fields, quest_play_of
from app.apps.rpg.rules import consequences as rule
from app.apps.rpg.session.campaign_state import upcast_campaign_document

FIXTURE = Path(__file__).resolve().parents[2] / "rpg" / "fixtures" / "campaign_documents_v5" / "aurelia.json.gz"
QUEST = "quest:engine"
CROWN = "faction:crown"
SMITH = "npc:smith"


def _document(effects: list[dict]) -> dict:
    document = upcast_campaign_document(json.loads(gzip.decompress(FIXTURE.read_bytes())))
    world = document["simulation_state"]["world_model"]
    world["groups"] = {CROWN: {"name": "The Crown"}}
    world["group_members"] = [{"group_id": CROWN, "members": ["npc:princess"]}]
    world["quests"] = {QUEST: {"id": QUEST, "title": "The Engine", "steps": [{"id": "decide", "summary": "Decide", "any_of": [
        {"all_of": [{"talk": "npc:princess"}], "sets": [{"fact": "engine", "value": "mended", "told": "The engine runs."}]},
        {"all_of": [{"talk": "npc:princess"}], "sets": [{"fact": "engine", "value": "broken", "told": "It is gone."}]},
    ]}]}, "quest:later": {"id": "quest:later", "title": "Later", "status": "available"}}
    world["fact_effects"] = effects
    return document


def _decided(document: dict, branch: int) -> tuple[dict, list, list[str]]:
    applied = [c.QuestStepCompleted(quest_id=QUEST, stage=1, step_id="decide", branch=branch)]
    made, lines = rule.consequences(document["simulation_state"], applied)
    after, _ = reduce(document, made)
    return after, made, lines


def test_a_way_taken_leaves_its_fact_known_with_its_line() -> None:
    after, made, lines = _decided(_document([]), 1)
    assert made == [c.FactSet(fact_id="engine", value="broken", source=f"{QUEST}:decide", told="It is gone.")]
    assert lines == ["It is gone."]
    assert rule.what_has_changed(after["simulation_state"]) == ["It is gone."]
    assert after["state"]["what_has_changed"] == ["It is gone."]


def test_one_time_effects_fire_when_their_condition_comes_to_hold_and_a_band_change_is_told() -> None:
    effects = [{"when": {"engine": "mended"}, "standing": {"group": CROWN, "delta": 30}},
               {"when": {"engine": "mended"}, "quest": {"opens": "quest:later"}}]
    after, made, lines = _decided(_document(effects), 0)
    assert c.StandingChanged(group_id=CROWN, delta=30, source="engine") in made
    assert any(isinstance(change, c.QuestOffered) and change.quest_id == "quest:later" for change in made)
    assert "The Crown now regards you as respected." in lines
    assert after["simulation_state"]["group_standing"] == {CROWN: 30}
    again, _ = rule.consequences(after["simulation_state"], [])
    assert again == []  # nothing new holds: nothing fires again


def test_effects_that_hold_are_read_by_the_rules_that_own_them() -> None:
    effects = [{"when": {"engine": "mended"}, "price": {"provider": SMITH, "percent": -10, "why": "power"}},
               {"when": {"engine": "broken"}, "closes": {"provider": SMITH}},
               {"when": {"engine": "mended"}, "place": {"location": "location:x", "line": "It hums."}},
               {"when": {"engine": "broken"}, "quest": {"closes": "quest:later"}}]
    mended, _, _ = _decided(_document(effects), 0)
    simulation = mended["simulation_state"]
    assert rule.price_factor(simulation, SMITH, "") == (pytest.approx(0.9), ["power"])
    assert rule.place_lines(simulation, "location:x") == ["It hums."]
    assert rule.closed_providers(simulation) == set()
    broken, _, lines = _decided(_document(effects), 1)
    assert rule.closed_providers(broken["simulation_state"]) == {SMITH}
    assert not rule.quest_open(broken["simulation_state"], {"id": "quest:later"})
    assert rule.quest_open(simulation, {"id": "quest:later"})


def test_a_quest_requires_and_forbids_facts() -> None:
    after, _, _ = _decided(_document([]), 0)
    simulation = after["simulation_state"]
    assert rule.quest_open(simulation, {"id": "q", "requires": {"engine": "mended"}})
    assert not rule.quest_open(simulation, {"id": "q", "forbids": {"engine": "mended"}})
    assert not rule.quest_open(simulation, {"id": "q", "requires": {"engine": "broken"}})


def test_a_waiver_is_given_once() -> None:
    document = _document([{"waive": {"provider": "npc:orik", "offer": "night", "why": "a welcome"}}])
    simulation = document["simulation_state"]
    simulation["world_model"]["offers"] = {"npc:orik": [{"offer_id": "npc:orik:night", "label": "A night"}]}
    assert rule.waived(simulation, "npc:orik", "night") == "a welcome"
    made, _ = rule.consequences(simulation, [c.ServiceReserved(offer_id="npc:orik:night", service_kind="lodging")])
    after, _ = reduce(document, made)
    assert rule.waived(after["simulation_state"], "npc:orik", "night") == ""


def test_group_standing_shapes_the_stance_of_its_members() -> None:
    after, _, _ = _decided(_document([{"when": {"engine": "broken"}, "standing": {"group": CROWN, "delta": -60}}]), 1)
    assert rule.standing_with(after["simulation_state"], "npc:princess") == (CROWN, -60)
    assert rule.standing_band(-60) == "hostile" and rule.standing_band(0) == "neutral" and rule.standing_band(55) == "trusted"


def test_an_ending_tells_its_epilogue_from_the_facts_the_hero_knows() -> None:
    after, _, _ = _decided(_document([]), 0)
    after["simulation_state"]["world_model"]["quests"][QUEST]["tier"] = "finale"
    ended = [c.QuestStatusChanged(quest_id=QUEST, status="completed")]
    assert rule.epilogue(after["simulation_state"], ended) == ["The engine runs."]
    assert rule.epilogue(after["simulation_state"], []) == []


def test_the_sections_round_trip_the_facts_a_way_leaves() -> None:
    row = {"id": QUEST, "sets": [{"fact": "done", "value": True, "told": "Done."}], "requires": {"engine": "mended"},
           "steps": [{"id": "decide", "summary": "Decide", "any_of": [
               {"all_of": [{"talk": "npc:a"}], "sets": [{"fact": "engine", "value": "mended", "told": "Runs."}]},
               {"all_of": [{"talk": "npc:b"}], "told": "Gone."}]}]}
    play = QuestPlay.model_validate(quest_play_of(row))
    assert quest_canon_fields(play) == {key: row[key] for key in ("steps", "sets", "requires")}
    with pytest.raises(ValueError):
        FactEffect.model_validate({"standing": {"group": CROWN, "delta": 5}})  # once, it needs a condition
    with pytest.raises(ValueError):
        FactEffect.model_validate({"when": {"a": 1}, "place": {"location": "l", "line": "x"},
                                   "closes": {"provider": SMITH}})  # one effect


def test_a_fact_can_replace_a_persons_day_or_send_them_away() -> None:
    from app.apps.rpg.rules.routines import clock, whereabouts

    document = _document([{"when": {"engine": "broken"}, "whereabouts": {"npc": "npc:princess", "location": ""}}])
    world = document["simulation_state"]["world_model"]
    world["npcs"]["npc:princess"] = {"id": "npc:princess", "name": "The Princess", "location_id": "location:x"}
    simulation = document["simulation_state"]
    assert whereabouts(simulation, clock(simulation))["npc:princess"].location_id == "location:x"
    broken, _, _ = _decided(document, 1)
    assert whereabouts(broken["simulation_state"], clock(simulation))["npc:princess"].location_id == ""  # gone


def test_a_fact_written_pulls_a_pressure_lever() -> None:
    from app.apps.rpg.rules.pressures import lever_pulls

    simulation = _document([])["simulation_state"]
    simulation["causal_world_runtime"] = {"pressure_plan": {"pressures": [{
        "pressure_id": "p:unrest", "name": "Unrest", "region_id": "",
        "levers": [{"action": "fact:engine=broken", "effect": "raise", "amount": 10}]}]}}
    pulled: list[dict] = []

    def pull(runtime, pulls):
        pulled.append(dict(pulls))
        return runtime, None

    lever_pulls(simulation, [c.FactSet(fact_id="engine", value="mended")], pull=pull)
    lever_pulls(simulation, [c.FactSet(fact_id="engine", value="broken")], pull=pull)
    assert pulled[0] == {} and set(pulled[1]) == {"p:unrest"}  # only the value the lever names pulls it
