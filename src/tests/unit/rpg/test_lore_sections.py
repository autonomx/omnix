"""A world written as lore plays from its lore (RQ-2.0; genesis/worlds/lore_sections.py)."""
from __future__ import annotations

from app.apps.rpg.genesis.worlds.lore_sections import DERIVED_TRAVEL_TIME, lore_location_rows, lore_routes, lore_rows

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
