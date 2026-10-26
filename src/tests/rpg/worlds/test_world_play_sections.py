"""A world's own economy, routines, knowledge, pressures and bestiary numbers are validated and played (RQ-2.0)."""
from __future__ import annotations

from types import SimpleNamespace

from app.apps.rpg.genesis.worlds.published_world_setup import bestiary_mechanics, session_world_model
from app.apps.rpg.genesis.worlds.world_play_sections import (
    authorship,
    parse_play_sections,
    play_section_findings,
)


def _canon(**sections) -> dict:
    canon = {
        "regions": [{"id": "region:vale", "name": "The Vale", "capital": "loc:hearth"}],
        "characters": [
            {"id": "npc:brindle", "name": "Brindle Ash", "role": "shopkeeper"},
            {"id": "npc:liora", "name": "Liora Fen", "role": "guide and first companion"},
        ],
        "items": [
            {"id": "item:lantern-bread", "name": "Lantern Bread", "type": "food", "effect": "restores stamina"},
            {"id": "item:echo-fang", "name": "Echo Fang", "type": "material"},
        ],
        "bestiary": [{"id": "monster:echo-wolf", "name": "Echo Wolf", "threat": "medium", "weakness": "silence"}],
        "economy": {"currency": "silver", "typical_prices": {"meal": "1 silver"}},
    }
    for key, value in sections.items():
        if key == "providers":
            canon["economy"]["providers"] = value
        else:
            canon[key] = value
    return canon


def _revision(canon: dict) -> SimpleNamespace:
    return SimpleNamespace(
        world_id="world:vale",
        revision=3,
        canon=canon,
        topology={
            "locations": [
                {"id": "loc:hearth", "name": "Hearth Square", "region_id": "region:vale"},
                {"id": "loc:market", "name": "Lantern Market", "region_id": "region:vale"},
            ],
            "routes": [{"id": "route:1", "from": "loc:hearth", "to": "loc:market", "travel_time": "10 minutes"}],
        },
        entity_manifest={},
    )


_ECONOMY = [
    {
        "provider_id": "npc:brindle",
        "location_id": "loc:market",
        "sells": [
            {"offer_key": "bread", "service": "shop_goods", "name": "Lantern Bread", "item_id": "item:lantern-bread",
             "price": {"copper": 6}, "stock": 12, "restock_per_day": 4},
        ],
        "buys": {"item_types": ["material"], "price_fraction": 0.4},
    }
]
_ROUTINES = [
    {"npc_id": "npc:liora", "schedule": [{"from_hour": 6, "to_hour": 18, "location_id": "loc:hearth"},
                                          {"from_hour": 18, "to_hour": 24, "location_id": "loc:market"}],
     "goals": [{"goal_id": "goal:gate", "summary": "Find out who opened the Meridian Gate.", "priority": 3}]}
]
_KNOWLEDGE = [
    {"npc_id": "npc:liora", "facts": [{"fact_id": "fact:gate", "text": "The gate opens at moonrise.",
                                       "shares": "when_trusted", "trust_needed": 20}]}
]
_PRESSURES = [
    {"pressure_id": "pressure:wolves", "name": "Echo wolves on the road", "region_id": "region:vale",
     "dimension": "trade_access", "severity": 55, "trend": "escalating",
     "levers": [{"action": "defeat:monster:echo-wolf", "effect": "lower", "amount": 10}]}
]


def test_a_world_without_play_sections_is_played_from_its_lore() -> None:
    sections, findings = parse_play_sections(_canon())

    assert findings == ()
    assert authorship(sections) == {section: "derived" for section in
                                    ("economy", "routines", "knowledge", "pressures", "bestiary")}
    model = session_world_model(_revision(_canon()), SimpleNamespace(starting_location_id="loc:hearth"))
    assert model["authorship"]["economy"] == "derived"
    assert model["routines"] == [] and model["pressures"] == []


def test_a_world_that_writes_its_economy_is_played_as_written() -> None:
    canon = _canon(providers=_ECONOMY, routines=_ROUTINES, knowledge=_KNOWLEDGE, pressures=_PRESSURES)

    model = session_world_model(_revision(canon), SimpleNamespace(starting_location_id="loc:hearth"))

    assert model["authorship"] == {"economy": "authored", "routines": "authored", "knowledge": "authored",
                                   "pressures": "authored", "bestiary": "derived"}
    provider = model["providers"]["npc:brindle"]
    assert provider["location_id"] == "loc:market"  # where the world puts her, not where her role guesses
    assert provider["buys"] == {"item_types": ["material"], "price_fraction": 0.4}
    [offer] = model["offers"]["npc:brindle"]
    assert offer["price"] == {"gold": 0, "silver": 0, "copper": 6}
    assert offer["stock"] == 12 and offer["restock_per_day"] == 4
    assert offer["effects"]["items_added"][0]["item_id"] == "item:lantern-bread"
    assert model["locations"]["loc:market"]["services"] == ["shop_goods"]
    assert model["locations"]["loc:hearth"]["services"] == []
    assert model["routines"][0]["schedule"][1]["location_id"] == "loc:market"
    assert model["knowledge"][0]["facts"][0]["shares"] == "when_trusted"
    assert model["pressures"][0]["trend"] == "escalating"


def test_a_creature_fights_with_its_written_numbers_and_drops_its_loot() -> None:
    canon = _canon()
    canon["bestiary"][0].update({
        "stats": {"level": 4, "hp": 22, "defense": 13, "damage_min": 2, "damage_max": 7, "xp_value": 80},
        "behaviour": "flees_when_hurt",
        "loot": [{"item_id": "item:echo-fang", "chance": 0.5}],
    })

    wolf = bestiary_mechanics(_revision(canon))["creatures"]["monster:echo-wolf"]

    assert (wolf["hp"], wolf["defense"], wolf["xp_value"]) == (22, 13, 80)
    assert wolf["behaviour"] == "flees_when_hurt"
    assert wolf["loot"] == [{"item_id": "item:echo-fang", "chance": 0.5, "quantity": 1}]
    assert authorship(parse_play_sections(canon)[0])["bestiary"] == "authored"


def test_broken_or_dangling_sections_are_release_findings() -> None:
    canon = _canon(
        providers=[{"provider_id": "npc:nobody", "sells": [{"offer_key": "x", "service": "shop_goods", "name": "X",
                                                             "item_id": "item:missing", "price": {"silver": 1}}]}],
        routines=[{"npc_id": "npc:liora", "schedule": [{"from_hour": 20, "to_hour": 8, "location_id": "loc:hearth"}]}],
        knowledge=[{"npc_id": "npc:liora", "facts": [{"fact_id": "f", "text": "t", "shares": "for_price"}]}],
        pressures=[{"pressure_id": "p", "name": "P", "region_id": "region:atlantis"}],
    )

    findings = play_section_findings(canon, location_ids={"loc:hearth", "loc:market"}, region_ids={"region:vale"})

    assert "play_section_unknown_person:economy:npc:nobody" in findings
    assert "play_section_unknown_item:economy:item:missing" in findings
    assert "play_section_unknown_place:pressures:region:atlantis" in findings
    assert any(item.startswith("play_section_invalid:routines[0]:") and "end_after_it_starts" in item for item in findings)
    assert any(item.startswith("play_section_invalid:knowledge[0]:") and "needs_price" in item for item in findings)


def test_a_release_with_a_broken_play_section_is_not_launch_ready() -> None:
    import importlib.util
    from pathlib import Path

    from app.apps.rpg.genesis.worlds.contracts import WorldReleaseDocument, WorldRevisionDocument
    from app.apps.rpg.genesis.worlds.semantic_validation import certify_world_release
    from app.apps.rpg.genesis.worlds.world_bundle import parse_world_bundle_archive
    from app.apps.rpg.world.map_grid_contracts import GridMapDefinition

    root = Path(__file__).resolve().parents[4] / "resources/examples/rpg/world-bundles/aurelia-echoes-beyond-the-gate"
    spec = importlib.util.spec_from_file_location("aurelia_materialize_play", root / "materialize.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload = parse_world_bundle_archive(module._build_bundle(root)).payload
    revision = WorldRevisionDocument.model_validate(payload.world_revisions[0]["document"])
    release = WorldReleaseDocument.model_validate(payload.world_releases[0]["document"])
    definitions = {  # the revision's own map definitions (each world revision has its own)
        row["map_id"]: GridMapDefinition.model_validate(row["document"]) for row in payload.map_definitions
        if int(row["document"]["world_revision"]) == revision.revision
    }

    assert certify_world_release(revision, release, definitions).certification["launch_ready"] is True

    canon = dict(revision.canon)
    canon["routines"] = [{"npc_id": "npc:nobody", "schedule": []}]
    broken = revision.model_copy(update={"canon": canon})
    certified = certify_world_release(broken, release, definitions)

    assert certified.certification["launch_ready"] is False
    assert "play_section_unknown_person:routines:npc:nobody" in certified.certification["missing_requirements"]


def test_a_world_with_creatures_starts_with_a_ticking_clock_and_its_own_pressures_win() -> None:
    from app.apps.rpg.genesis.worlds.published_pressures import pressure_planning, published_causal_runtime
    from app.apps.rpg.world.causal_runtime import advance_causal_runtime

    derived, source = pressure_planning(_canon())
    assert source == "derived"
    [road] = derived["pressure_plan"]["pressures"]
    assert road["pressure_id"] == "pressure:roads:vale" and road["severity"] == 40.0
    assert road["levers"] == [{"action": "defeat:monster:echo-wolf", "effect": "lower", "amount": 8.0}]

    authored, source = pressure_planning(_canon(pressures=_PRESSURES))
    assert source == "authored"
    assert [row["pressure_id"] for row in authored["pressure_plan"]["pressures"]] == ["pressure:wolves"]

    runtime = published_causal_runtime(_canon(pressures=_PRESSURES))
    for tick in range(1, 11):
        runtime, _events = advance_causal_runtime(runtime, tick=tick)
    cells = runtime["state"]["cells"]
    assert cells["pressure:wolves"]["values"]["pressure_severity"] > 55  # escalating
    assert cells["region:vale"]["values"]["trade_access"] < 45  # and the roads suffer for it

    no_creatures = _canon()
    no_creatures["bestiary"] = []
    assert published_causal_runtime(no_creatures) == {}
