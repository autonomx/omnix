"""A world written as lore plays from its lore (RQ-2.0; genesis/worlds/lore_sections.py)."""
from __future__ import annotations

from app.apps.rpg.genesis.worlds.lore_sections import (
    DERIVED_JOURNEY_TIME,
    DERIVED_TRAVEL_TIME,
    joined_routes,
    lore_location_rows,
    lore_routes,
    lore_rows,
)

CANON = {"entities": {
    "ent:actors:mara": {"id": "ent:actors:mara", "kind": "npc", "name": "Mara Vey", "location_id": "ent:places:station",
                        "short_summary": "A memory courier, carrying copies between clinics.", "goal": "Find her past",
                        "hidden_truth": "She is a composite", "speech_style": "clipped"},
    "ent:regions:sump": {"id": "ent:regions:sump", "kind": "region", "name": "The Sump", "short_summary": "Low and wet."},
    "ent:regions:spires": {"id": "ent:regions:spires", "kind": "region", "name": "The Spires"},
    "ent:places:station": {"id": "ent:places:station", "kind": "location", "name": "Black Rain Station",
                           "region_id": "ent:regions:sump", "short_summary": "Dark water."},
    "ent:places:market": {"id": "ent:places:market", "kind": "location", "name": "Night Market", "region_id": "ent:regions:sump"},
    "ent:places:clinic": {"id": "ent:places:clinic", "kind": "location", "name": "Clinic", "region_id": "ent:regions:spires"},
    "ent:threats:wasps": {"id": "ent:threats:wasps", "kind": "cyberpunk_threat", "name": "Glass Wasps",
                          "threat_level": "dangerous", "capabilities": ["Swarm cutting"], "weaknesses": ["Cold", "Lures"]},
}}


def test_each_section_is_the_worlds_as_written_else_taken_from_its_lore() -> None:
    [mara] = lore_rows(CANON, "characters")
    assert (mara["name"], mara["role"], mara["location_id"]) == ("Mara Vey", "memory courier", "ent:places:station")
    assert mara["goals"] == ["Find her past"] and mara["secrets"] == ["She is a composite"]
    assert [row["name"] for row in lore_rows(CANON, "regions")] == ["The Sump", "The Spires"]
    [wasps] = lore_rows(CANON, "bestiary")
    assert (wasps["threat"], wasps["traits"], wasps["weakness"]) == ("dangerous", ["Swarm cutting"], "Cold, Lures")
    authored = {**CANON, "characters": [{"id": "npc:bran", "name": "Bran"}]}
    assert lore_rows(authored, "characters") == [{"id": "npc:bran", "name": "Bran"}]  # what a world wrote stands


def test_places_listed_by_bare_id_are_filled_in_and_roads_follow_the_regions() -> None:
    rows = lore_location_rows(CANON, {"locations": ["ent:places:station", "ent:places:market", "ent:places:clinic"]})
    assert [(row["name"], row["region_id"]) for row in rows] == [
        ("Black Rain Station", "ent:regions:sump"), ("Night Market", "ent:regions:sump"), ("Clinic", "ent:regions:spires")]
    roads = {(road["from"], road["to"]) for road in lore_routes(rows, lore_rows(CANON, "regions"))}
    assert roads == {("ent:places:station", "ent:places:market"),  # within a region, each to the others
                     ("ent:places:station", "ent:places:clinic")}  # and the regions joined through their first places
    assert all(road["travel_time"] == DERIVED_TRAVEL_TIME for road in lore_routes(rows, []))


def test_a_place_the_world_s_roads_leave_unreached_is_joined_to_them() -> None:
    """The playtest: Aurelia's four roads never reached Valecourt or the Hollow Meridian, two of its quests' places."""
    places = [{"id": "grove", "region_id": "march"}, {"id": "ruins", "region_id": "deep"},
              {"id": "meridian", "region_id": "deep"}, {"id": "capital", "region_id": "heart"},
              {"id": "village", "region_id": "march"}]
    regions = [{"id": "march", "capital": "village"}, {"id": "heart"}, {"id": "deep"}]
    authored = [{"id": "road:1", "from": "grove", "to": "village", "travel_time": "1 hour"},
                {"id": "road:2", "from": "village", "to": "ruins", "travel_time": "3 hours"}]
    roads = joined_routes(authored, places, regions, start="grove")
    assert roads[:2] == authored  # the world's roads stand
    added = {(road["from"], road["to"]): road["travel_time"] for road in roads[2:]}
    assert added == {("ruins", "meridian"): DERIVED_TRAVEL_TIME,  # a reached place of its own region
                     ("village", "capital"): DERIVED_JOURNEY_TIME}  # else the nearest region's capital
    assert joined_routes(roads, places, regions, start="grove") == roads  # all reached: nothing more


def test_a_role_from_a_summary_ends_where_its_verb_begins() -> None:
    """The intent gate: a six-word cut made Vesper-9's fixer "fixer arranges documents" (and so "the documents")."""
    from app.apps.rpg.genesis.worlds.lore_sections import _role

    assert _role({"description": "A fixer arranges documents, rooms and rides."}) == "fixer"
    assert _role({"description": "A memory courier transports unnetworked copies."}) == "memory courier"
    assert _role({"description": "A crane operator and elected Red Knives strike coordinator can stop the docks."}) == (
        "crane operator and elected Red Knives strike coordinator")
    assert _role({"role": "innkeeper"}) == "innkeeper"  # as written


def test_a_lore_worlds_groups_are_its_own() -> None:
    canon = {"entities": [{"id": "ent:groups:union", "kind": "group", "name": "Red Knives Union",
                           "short_summary": "The dock workers' union."}]}
    assert lore_rows(canon, "groups") == [{"id": "ent:groups:union", "name": "Red Knives Union",
                                           "summary": "The dock workers' union."}]


def test_a_lore_entitys_hidden_truth_stays_out_of_what_anyone_may_see() -> None:
    """The review: Vesper-9's lore keeps each one's hidden truth inside the description, and a close look printed it."""
    told = "A fixer at a booth. He once served Kestrel intelligence and draws a dead medic's pension. He keeps three lists."
    canon = {"entities": {
        "a:oren": {"id": "a:oren", "kind": "actor", "name": "Oren Pike", "description": told,
                   "hidden_truth": "He once served Kestrel intelligence and still draws a pension through a dead medic."},
        "p:station": {"id": "p:station", "kind": "place", "name": "Black Rain Station", "short_summary": "An interchange.",
                      "description": "An interchange of dark water. Platform Zero receives a wartime train.",
                      "hidden_truth": "Platform Zero receives a driverless wartime train on irregular nights."},
    }}
    [oren] = lore_rows(canon, "characters")
    assert oren["biography"] == "A fixer at a booth. He keeps three lists." and oren["secrets"]
    [station] = lore_location_rows(canon, {})
    assert station["description"] == "An interchange of dark water."
