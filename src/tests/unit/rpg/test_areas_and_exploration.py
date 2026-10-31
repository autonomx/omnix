"""Areas filled in as the hero approaches, and what exploring finds (evolution roadmap EV-10): an area's entries within
its budget (authored detail counted), a site's fixed shape, a capped share folded in a turn, places first, a hidden
place found by a seeded search, and a site's rooms met and cleared."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from app.apps.rpg.foundation.state import changes as c
from app.apps.rpg.foundation.state.proposals import Proposal
from app.apps.rpg.foundation.state.reducer import reduce
from app.apps.rpg.narration.game_master.area_call import checked, open_areas
from app.apps.rpg.rules import exploration
from app.apps.rpg.rules.inventions import fold_area_entry
from app.apps.rpg.session.campaign_state import upcast_campaign_document
from app.apps.rpg.session.turn.proposals import AREA_ENTRIES_PER_TURN, fold_in

FIXTURE = Path(__file__).resolve().parents[2] / "rpg" / "fixtures" / "campaign_documents_v5" / "aurelia.json.gz"
MARCH, VILLAGE, GROVE = "region:starfall-march", "location:aurelia:starfall-village", "location:aurelia:arrival-grove"
SITE = {"kind": "site", "name": "Rootfall Hollow", "description": "A hollow under the old roots.", "difficulty": 5,
        "play": {"roads": [{"to": GROVE, "travel_time": "20 minutes"}]},
        "site": {"theme": "roots and old bones", "rooms": [{"name": "the root gate"}, {"name": "the bone pit"}]}}


def _document() -> dict:
    return upcast_campaign_document(json.loads(gzip.decompress(FIXTURE.read_bytes())))


def _folded(document: dict, entry: dict, area: str = MARCH) -> tuple[dict, list]:
    folded = fold_area_entry(document, {"area_id": area, "entry": entry})
    assert not folded.refused, folded.refused
    return reduce(document, folded.changes)[0], folded.changes


def test_an_area_holds_its_budget_and_authored_detail_counts_toward_it() -> None:
    document = _document()
    place = {"kind": "place", "name": "The Old Mill", "play": {"roads": [{"to": VILLAGE}]}}
    assert fold_area_entry(document, {"area_id": MARCH, "entry": place}).refused == \
        "region:starfall-march holds its 3 of place already"  # its three authored places fill a medium area's
    document, made = _folded(document, {"kind": "rumour", "told": "Wolves were heard past the grove."})
    assert [change.type for change in made] == ["area_detailed", "rumour_spread", "rumour_spread", "rumour_spread"]
    document, _ = _folded(document, {"kind": "lore", "told": "The march was farmland before the gate opened."})
    assert document["simulation_state"]["area_detail"][MARCH]["lore"] == ["The march was farmland before the gate opened."]
    assert fold_area_entry(document, {"area_id": "region:nowhere", "entry": place}).refused == "no such area in this world"


def test_a_site_has_a_fixed_shape_hidden_until_found() -> None:
    document, made = _folded(_document(), SITE)
    site_id = made[0].entry_id
    world = document["simulation_state"]["world_model"]
    assert world["locations"][site_id]["hidden"] is True and site_id not in world["locations"][GROVE]["exits"].values()
    rooms = made[0].play["site"]["rooms"]
    assert [room["name"] for room in rooms] == ["the root gate", "the bone pit"]
    assert rooms[0]["from"] == site_id and rooms[1]["from"] == rooms[0]["id"]
    assert all(room["creature_id"] in document["simulation_state"]["campaign_mechanics"]["creatures"] for room in rooms)
    assert rooms[1].get("loot_item_id")  # the last room holds the site's reward
    assert _folded(_document(), SITE)[1][0].play == made[0].play  # its layout is the campaign's, seeded


def test_a_hidden_place_is_found_by_a_seeded_search_and_joins_the_roads() -> None:
    document, made = _folded(_document(), SITE)
    site_id = made[0].entry_id
    assert exploration.hidden_here(document["simulation_state"])[0]["id"] == site_id  # the hero stands in the grove
    searched = None
    for turn in range(10):
        document["state"]["turn_count"] = turn
        searched = exploration.explore(document)
        if searched.changes:
            break
    assert searched is not None and searched.changes == [c.SiteFound(location_id=site_id, told="You find Rootfall Hollow.")]
    found, _ = reduce(document, searched.changes)
    world = found["simulation_state"]["world_model"]
    assert world["locations"][GROVE]["exits"]["rootfall hollow"] == site_id
    assert found["simulation_state"]["exploration"]["found"] == [site_id]
    elsewhere, _ = reduce(_document(), [c.LocationChanged(location_id=VILLAGE, location_name="Starfall Village")])
    assert exploration.explore(elsewhere).lines == ["You search the area but find nothing this time."]


def test_a_rooms_encounter_stands_until_it_is_beaten_and_its_loot_clears_it_too() -> None:
    document, made = _folded(_document(), SITE)
    rooms = made[0].play["site"]["rooms"]
    inside, _ = reduce(document, [c.LocationChanged(location_id=rooms[0]["id"], location_name="the root gate")])
    simulation = inside["simulation_state"]
    assert exploration.room_foe(simulation) == rooms[0]["creature_id"]
    cleared = exploration.rooms_cleared(simulation, [c.CombatEnded(outcome="victory")])
    assert cleared == [c.RoomCleared(site_id=made[0].entry_id, room_id=rooms[0]["id"], how="beaten")]
    after, _ = reduce(inside, cleared)
    assert exploration.room_foe(after["simulation_state"]) == ""


def test_a_turn_folds_in_a_capped_share_places_first() -> None:
    document = _document()
    document["simulation_state"]["world_model"]["gm_guide"] = {"areas": {MARCH: {"counts": {"lore": 12, "site": 1}}}}
    lore = [Proposal(proposal_id=f"area:x:{index}", kind="gm_area", source="area", after_revision=0, reason="fill",
                     payload={"area_id": MARCH, "entry": {"kind": "lore", "told": f"A tale, the {index}th."}})
            for index in range(11)]
    site = Proposal(proposal_id="area:x:site", kind="gm_area", source="area", after_revision=0, reason="fill",
                    payload={"area_id": MARCH, "entry": SITE})
    _, record = fold_in(document, [*lore, site])
    assert len(record.folded) == AREA_ENTRIES_PER_TURN and record.folded[0].proposal_id == "area:x:site"


def test_the_area_call_keeps_only_what_the_area_still_wants() -> None:
    document = _document()
    # The grove's region, and the one a road from any of its places reaches (the village's to Skybridge Pass): the
    # lead time is the hero's whole stay in the area, not the step before leaving it (EV-10's timed gate).
    assert open_areas(document) == [MARCH, "region:cloudspine"]
    kept, dropped = checked(document, MARCH, [
        {"kind": "place", "name": "The Old Mill"}, {"kind": "person", "name": "Liora Fen"},
        {"kind": "site", "name": "Rootfall Hollow"}, {"kind": "site", "name": "Second Hollow"},
        {"kind": "rumour", "told": "Wolves."}])
    assert [row["name"] if row.get("name") else row["told"] for row in kept] == ["Rootfall Hollow", "Wolves."]
    assert dropped == ["place: no kind the area still wants", "person: no kind the area still wants",
                       "site: no kind the area still wants"]


def test_a_rooms_grid_is_the_campaigns_and_its_hazard_is_met_once() -> None:
    document, made = _folded(_document(), SITE)
    rooms = made[0].play["site"]["rooms"]
    grid = rooms[0]["map"]
    assert grid["map_id"] == f"map:{rooms[0]['id']}" and len(grid["rows"]) == grid["height"]
    assert document["simulation_state"]["world_model"]["locations"][rooms[0]["id"]]["map_id"] == grid["map_id"]
    layer = document["simulation_state"]["lore_layer"]["entries"][made[0].entry_id]
    layer["play"]["site"]["rooms"][0]["hazard"] = {"check": "climb", "difficulty": 30, "told": "A ledge.",
                                                   "passed": "You climb.", "failed": "You slip", "damage": 4}
    inside, _ = reduce(document, [c.LocationChanged(location_id=rooms[0]["id"], location_name="the root gate")])
    met, lines = exploration.room_hazard(inside["simulation_state"], turn_key="7")
    assert [change.type for change in met] == ["room_cleared", "hp_changed"] and lines == ["A ledge.", "You slip (4 damage)."]
    after, _ = reduce(inside, met)
    assert exploration.room_hazard(after["simulation_state"], turn_key="8") == ([], [])  # met once


def test_a_journey_into_a_site_stops_at_each_room_that_holds_its_encounter() -> None:
    """Review: "go to the innermost chamber" from the site walked past every room's creature to the boss."""
    from app.apps.rpg.session.turn.planning import PlannedAction
    from app.apps.rpg.session.turn.travel import resolve_travel

    document, made = _folded(_document(), SITE)
    site_id, rooms = made[0].entry_id, made[0].play["site"]["rooms"]
    document, _ = reduce(document, [c.SiteFound(location_id=site_id),
                                    c.LocationChanged(location_id=site_id, location_name="Rootfall Hollow")])
    went = resolve_travel(PlannedAction(mechanic="travel", target_id=rooms[-1]["id"]), document)
    assert went.destination == rooms[0]["id"]  # the first room's encounter is met before going on
