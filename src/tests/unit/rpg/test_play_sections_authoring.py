"""How a world plays, written in the world editor (RQ-4.1): World Forge's draft from the lore, the draft written into
canon at publication, and the findings that name what the world lacks (genesis/worlds/play_section_*.py)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.apps.rpg.genesis.worlds.builtin_worlds import STARTER, world_source
from app.apps.rpg.genesis.worlds.contracts import WorldReleaseDocument, WorldRevisionDocument
from app.apps.rpg.genesis.worlds.play_section_generation import generate_play_sections
from app.apps.rpg.genesis.worlds.play_section_publication import (
    PLAY_SECTIONS_KEY,
    authored_play_sections,
    merge_authored_play_sections,
)
from app.apps.rpg.genesis.worlds.published_world_setup import session_world_model
from app.apps.rpg.genesis.worlds.world_play_sections import (
    PlaySectionsDraft,
    authorship,
    draft_findings,
    parse_play_sections,
    play_section_findings,
    play_sections_document,
    unknown_creatures,
    with_play_sections,
)
from app.apps.rpg.genesis.worlds.world_source import compile_world

# A world written as lore (as Vesper-9 is): people, places, regions, items, a creature, a quest and a pressure,
# all as entities, and no section of how it plays.
CANON = {
    "economy": {"typical_prices": {"meal": "2 silver"}},
    "entities": {
        "ent:actors:mara": {"id": "ent:actors:mara", "kind": "npc", "name": "Mara Vey", "role": "innkeeper",
                            "location_id": "ent:places:station", "goal": "Find her past",
                            "public_truth": "She runs the station inn.", "hidden_truth": "She is a composite."},
        "ent:actors:oren": {"id": "ent:actors:oren", "kind": "npc", "name": "Oren", "role": "merchant",
                            "location_id": "ent:places:market"},
        "ent:regions:sump": {"id": "ent:regions:sump", "kind": "region", "name": "The Sump"},
        "ent:places:station": {"id": "ent:places:station", "kind": "location", "name": "Black Rain Station",
                               "region_id": "ent:regions:sump"},
        "ent:places:market": {"id": "ent:places:market", "kind": "location", "name": "Night Market",
                              "region_id": "ent:regions:sump"},
        "ent:equipment:ration": {"id": "ent:equipment:ration", "kind": "equipment", "name": "Ration Pack",
                                 "item_type": "food", "short_summary": "A day of food."},
        "ent:threats:wasps": {"id": "ent:threats:wasps", "kind": "cyberpunk_threat", "name": "Glass Wasps",
                              "threat_level": "dangerous", "capabilities": ["Swarm cutting"]},
        "ent:quests:quiet": {"id": "ent:quests:quiet", "kind": "quest", "name": "Quiet the Market",
                             "pressure_ids": ["ent:pressures:blackout"]},
        "ent:pressures:blackout": {"id": "ent:pressures:blackout", "kind": "pressure", "name": "The Blackout",
                                   "place_ids": ["ent:places:market"],
                                   "short_summary": "Power fails and the market's supply runs short."},
    },
}
TOPOLOGY = {"locations": ["ent:places:station", "ent:places:market"]}


def _revision(canon=CANON):
    return SimpleNamespace(canon=canon, topology=TOPOLOGY, world_id="world:lore", revision=1, entity_manifest={})


def _places() -> set[str]:
    return {"ent:places:station", "ent:places:market"}


def test_world_forge_drafts_every_section_from_the_lore() -> None:
    draft = generate_play_sections(_revision())
    providers = {row["provider_id"]: row for row in draft["economy"]["providers"]}
    assert set(providers) == {"ent:actors:mara", "ent:actors:oren"}
    meals = [offer for offer in providers["ent:actors:mara"]["sells"] if offer["service"] == "meal"]
    assert meals and meals[0]["price"] == {"gold": 0, "silver": 2, "copper": 0}  # the world's own price
    goods = [offer for offer in providers["ent:actors:oren"]["sells"] if offer["service"] == "shop_goods"]
    assert {offer["item_id"] for offer in goods} == {"ent:equipment:ration"}  # only the world's own items
    [mara] = [row for row in draft["routines"] if row["npc_id"] == "ent:actors:mara"]
    assert mara["schedule"][0]["location_id"] == "ent:places:station"
    assert [goal["summary"] for goal in mara["goals"]] == ["Find her past"]
    [knows] = [row for row in draft["knowledge"] if row["npc_id"] == "ent:actors:mara"]
    assert [(fact["text"], fact["shares"]) for fact in knows["facts"]] == [
        ("She runs the station inn.", "freely"), ("She is a composite.", "when_trusted")]
    blackout = next(row for row in draft["pressures"] if row["pressure_id"] == "ent:pressures:blackout")
    assert (blackout["region_id"], blackout["dimension"]) == ("ent:regions:sump", "trade_access")
    assert blackout["levers"] == [{"action": "quest:ent:quests:quiet", "effect": "lower", "amount": 15.0}]
    assert any(row["pressure_id"].startswith("pressure:roads:") for row in draft["pressures"])  # the wasps' roads
    [wasps] = draft["bestiary"]
    assert wasps["id"] == "ent:threats:wasps" and wasps["stats"]["level"] == 3  # "dangerous": a medium threat
    # The draft is valid and names only what the world has.
    published = with_play_sections(CANON, PlaySectionsDraft.model_validate(draft))
    assert play_section_findings(published, location_ids=_places(), region_ids={"ent:regions:sump"}) == ()
    # Every section but the quests' steps, the world's consequences (EV-1) and its level budgets (EV-2), which are
    # their author's (a quest without steps is done by its places; a world without consequences remembers its facts
    # and changes nothing; one without budgets plays from the derived table).
    assert {section for section, source in authorship(parse_play_sections(published)[0]).items()
            if source != "authored"} == {"quests", "fact_effects", "group_members", "budgets"}


def test_world_forge_drafts_quest_steps_goal_beats_and_gear_for_sale() -> None:
    """EV-6: the drafts go as deep as the play sections do: a quest's steps from its places and giver, a first beat on
    each goal, and the world's gear that no one sells, by its first seller of goods, priced for its slot."""
    entities = {**CANON["entities"],
                "ent:quests:quiet": {**CANON["entities"]["ent:quests:quiet"], "locations": ["ent:places:market"],
                                     "giver_id": "ent:actors:mara"},
                "ent:equipment:baton": {"id": "ent:equipment:baton", "kind": "equipment", "name": "Shock Baton",
                                        "item_type": "weapon", "equipment": {"slot": "main_hand",
                                                                             "stats": {"damage_max": 3}}}}
    draft = generate_play_sections(_revision({**CANON, "entities": entities}))
    [quest] = draft["quests"]
    assert [step["ways"][0]["conditions"][0] for step in quest["steps"]] == [
        {"kind": "reach", "subject": "ent:places:market", "about": [], "count": 1, "target": ""},
        {"kind": "talk", "subject": "ent:actors:mara", "about": [], "count": 1, "target": ""}]
    [mara] = [row for row in draft["routines"] if row["npc_id"] == "ent:actors:mara"]
    assert mara["goals"][0]["beats"][0]["rumour"] == "Mara Vey is said to be working to find her past."
    goods = [offer for provider in draft["economy"]["providers"] for offer in provider["sells"]]
    assert any(offer["item_id"] == "ent:equipment:baton" for offer in goods)
    assert PlaySectionsDraft.model_validate(draft)


def test_a_section_the_world_wrote_is_kept_as_written() -> None:
    written = {**CANON, "routines": [{"npc_id": "ent:actors:oren", "schedule": [
        {"from_hour": 8, "to_hour": 20, "location_id": "ent:places:market", "activity": "trading"}]}]}
    draft = generate_play_sections(_revision(written))
    assert draft["routines"] == play_sections_document(written)["routines"]
    assert draft["knowledge"]  # the sections it did not write are drafted from the lore


def test_the_draft_is_the_whole_of_how_the_world_plays_once_written_into_canon() -> None:
    draft = PlaySectionsDraft.model_validate(generate_play_sections(_revision()))
    published = with_play_sections(CANON, draft)
    assert published["economy"]["typical_prices"] == {"meal": "2 silver"}  # the rest of its economy stays
    [wasps] = published["bestiary"]
    assert (wasps["name"], wasps["threat"], wasps["traits"]) == ("Glass Wasps", "dangerous", ["Swarm cutting"])
    # Read back, it is the draft; a section emptied again is played from the lore.
    assert play_sections_document(published) == draft.model_dump(mode="json", exclude_none=True)
    emptied = with_play_sections(published, PlaySectionsDraft())
    assert "routines" not in emptied and "providers" not in emptied["economy"]
    assert "stats" not in emptied["bestiary"][0] and emptied["bestiary"][0]["name"] == "Glass Wasps"
    assert set(authorship(parse_play_sections(emptied)[0]).values()) == {"derived"}


def test_findings_name_what_a_lore_world_lacks() -> None:
    draft = PlaySectionsDraft.model_validate({
        "economy": {"providers": [{"provider_id": "ent:actors:mara", "sells": [
            {"offer_key": "lamp", "service": "shop_goods", "name": "Lamp", "price": {"silver": 1},
             "item_id": "ent:equipment:lamp"}]}]},
        "routines": [{"npc_id": "ent:actors:nobody"}],
        "pressures": [{"pressure_id": "p", "name": "P", "region_id": "ent:regions:sump",
                       "levers": [{"action": "quest:ent:quests:quiet", "effect": "lower", "amount": 5}]}],
        "bestiary": [{"id": "ent:threats:ghost", "behaviour": "guards"}],
    })
    findings = play_section_findings(with_play_sections(CANON, draft), location_ids=_places(),
                                     region_ids={"ent:regions:sump"})
    assert findings == (
        "play_section_unknown_item:economy:ent:equipment:lamp",
        "play_section_unknown_person:routines:ent:actors:nobody",
    )  # Mara, the Sump and the quest are the world's own, as entities
    assert unknown_creatures(CANON, draft) == ("play_section_unknown_creature:bestiary:ent:threats:ghost",)
    assert [row["id"] for row in with_play_sections(CANON, draft)["bestiary"]] == ["ent:threats:wasps"]


def test_a_wrongly_shaped_draft_names_each_error() -> None:
    draft, findings = draft_findings({"routines": [{"npc_id": "n", "schedule": [
        {"from_hour": 9, "to_hour": 8, "location_id": "x"}]}], "extra": 1})
    assert draft is None
    assert "play_section_invalid:extra:Extra inputs are not permitted" in findings
    assert any(finding.startswith("play_section_invalid:routines.0.schedule.0:") for finding in findings)


def _starter() -> tuple[WorldRevisionDocument, WorldReleaseDocument]:
    compiled = compile_world(world_source(STARTER))
    return (WorldRevisionDocument.model_validate(compiled["world_revisions"][0]["document"]),
            WorldReleaseDocument.model_validate(compiled["world_releases"][0]["document"]))


def test_a_publication_writes_the_authors_draft_into_the_new_revision() -> None:
    revision, release = _starter()
    assert merge_authored_play_sections(revision, release, authored_play_sections({"metadata": {}})) == (
        revision, release)  # nothing saved: the publication is as compiled
    document = play_sections_document(revision.canon)
    offer = document["economy"]["providers"][0]["sells"][0]
    offer["price"] = {"gold": 3, "silver": 0, "copper": 0}
    world = {"metadata": {PLAY_SECTIONS_KEY: {"document": document}}}
    merged, merged_release = merge_authored_play_sections(revision, release, authored_play_sections(world))
    assert merged.revision == revision.revision and merged.content_hash != revision.content_hash
    assert merged_release.world_revision_hash == merged.content_hash
    assert merged.provenance["authored_play_sections"]
    played = session_world_model(merged, SimpleNamespace(starting_location_id=""))
    provider = document["economy"]["providers"][0]["provider_id"]
    priced = next(row for row in played["offers"][provider] if row["offer_id"].endswith(f":{offer['offer_key']}"))
    assert priced["price"] == {"gold": 3, "silver": 0, "copper": 0}


def test_a_publication_stops_at_a_draft_naming_what_the_world_lacks() -> None:
    revision, release = _starter()
    world = {"metadata": {PLAY_SECTIONS_KEY: {"document": {"routines": [{"npc_id": "npc:nobody"}]}}}}
    with pytest.raises(ValueError, match="world_play_sections_invalid:play_section_unknown_person:routines:npc:nobody"):
        merge_authored_play_sections(revision, release, authored_play_sections(world))
