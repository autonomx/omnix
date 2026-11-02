"""What the game master invents (evolution roadmap EV-0, part 2): the checks before an invention is played, the
effective world model it joins, the lore layer that keeps it, and its world's review (question 15, the canon id it
is published under)."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from app.apps.rpg.foundation.state import changes as c
from app.apps.rpg.foundation.state.reducer import reduce
from app.apps.rpg.rules import routines
from app.apps.rpg.rules.inventions import fold_invention, inventions
from app.apps.rpg.session import lore_review
from app.apps.rpg.session.campaign_state import upcast_campaign_document

FIXTURE = Path(__file__).resolve().parents[2] / "rpg" / "fixtures" / "campaign_documents_v5" / "aurelia.json.gz"
VILLAGE, GROVE = "location:aurelia:starfall-village", "location:aurelia:arrival-grove"
SECRET = "she hears the Meridian Gate whisper the protagonist's true Earth name"


def _document() -> dict:
    document = upcast_campaign_document(json.loads(gzip.decompress(FIXTURE.read_bytes())))
    document["simulation_state"]["world_model"]["npcs"]["npc:liora-fen"]["secrets"] = [SECRET]
    return document


def _played(document: dict, payload: dict) -> tuple[dict, list]:
    folded = fold_invention(document, payload)
    assert not folded.refused, folded.refused
    after, _ = reduce(document, folded.changes)
    return after, folded.changes


def test_an_invented_person_lives_in_the_world_and_keeps_their_day() -> None:
    document, made = _played(_document(), {
        "family": "person", "name": "Tamsin Reed", "description": "A ferrywoman who carries word between villages.",
        "play": {"location_id": VILLAGE, "role": "ferrywoman",
                 "schedule": [{"from_hour": 0, "to_hour": 24, "location_id": VILLAGE, "activity": "mending nets"}],
                 "knowledge": [{"text": "The river runs high this season.", "topics": ["river"]}]},
        "reason": "the village needs a messenger"})
    entry_id = made[0].entry_id
    assert entry_id == "gm:rpg_JLsRpC3rYtUWXQa5:tamsin-reed"
    simulation = document["simulation_state"]
    assert simulation["world_model"]["npcs"][entry_id]["name"] == "Tamsin Reed"
    assert routines.whereabouts(simulation, routines.clock(simulation))[entry_id].activity == "mending nets"
    layer = inventions(simulation)[entry_id]
    assert layer["family"] == "person" and layer["provenance"]["reason"] == "the village needs a messenger"


def test_an_invented_item_can_lie_somewhere_or_be_sold_within_the_levels_budget() -> None:
    blade = {"family": "item", "name": "Ashen Fang", "description": "A short blade gone grey with old fire.",
             "play": {"type": "weapon", "equipment": {"slot": "main_hand", "stats": {"damage_min": 1, "damage_max": 3}},
                      "location_id": GROVE}}
    document, made = _played(_document(), blade)
    ground = document["simulation_state"]["world_items"]["by_location"][GROVE]
    assert any(stack["item_id"] == made[0].entry_id and stack["equipment"]["slot"] == "main_hand" for stack in ground)
    too_strong = {**blade, "name": "Sunsplitter", "play": {**blade["play"], "equipment": {
        "slot": "main_hand", "stats": {"damage_max": 40}}}}
    assert fold_invention(_document(), too_strong).refused.startswith("its damage is outside the level's budget")
    sold = {**blade, "name": "Lantern Charm", "play": {"type": "trinket", "seller_id": "npc:brindle-gearwing",
                                                       "price_copper": 30}}
    document, made = _played(_document(), sold)
    offers = document["simulation_state"]["world_model"]["offers"]["npc:brindle-gearwing"]
    assert any(offer["label"] == "Lantern Charm" for offer in offers)


def test_an_invention_is_refused_when_it_clashes_names_a_secret_or_joins_no_road() -> None:
    document = _document()
    assert fold_invention(document, {"family": "person", "name": "Liora Fen", "play": {"location_id": VILLAGE}}).refused \
        == "'Liora Fen' clashes with an entry the world has"
    secret = {"family": "person", "name": "Mara Vell", "description": f"She knows that {SECRET}.",
              "play": {"location_id": VILLAGE}}
    assert fold_invention(document, secret).refused == "it names a secret"
    assert fold_invention(document, {"family": "place", "name": "Nowhere Hollow", "play": {"roads": []}}).refused \
        .startswith("a place joins the roads")
    weak = {"family": "creature", "name": "Glass Moth", "play": {"level": 1, "hp": 400, "damage_max": 3, "defense": 10}}
    assert "hp 400 is outside" in fold_invention(document, weak).refused
    rich = {"family": "quest", "name": "The Lost Ledger", "play": {"giver_id": "npc:orik-stonewake", "steps": [
        {"summary": "Find it", "conditions": [{"kind": "reach", "subject": VILLAGE}]}], "reward": {"xp": 99999}}}
    assert fold_invention(document, rich).refused.startswith("its reward is outside the level's budget")


def test_an_invented_place_joins_the_roads_both_ways() -> None:
    document, made = _played(_document(), {"family": "place", "name": "Reedmere Ford", "description": "A shallow ford.",
                                           "play": {"roads": [{"to": VILLAGE, "travel_time": "40 minutes"}]}})
    world = document["simulation_state"]["world_model"]
    assert world["locations"][VILLAGE]["exits"]["reedmere ford"] == made[0].entry_id
    assert any(route["from"] == made[0].entry_id and route["to"] == VILLAGE for route in world["routes"])


def test_drafts_go_where_question_15_says_and_an_approved_one_is_published_under_its_canon_id() -> None:
    assert lore_review.files_drafts({"metadata": {}}, guest=False)
    assert not lore_review.files_drafts({"metadata": {}}, guest=True)
    assert not lore_review.files_drafts({"metadata": {"world_bundle_import": {}}}, guest=False)
    assert lore_review.files_drafts({"metadata": {"world_bundle_import": {}, "lore_drafts": True}}, guest=False)
    assert lore_review.group_key("The Ashen Fang!") == lore_review.group_key("ashen fang") == "ashen fang"
    assert lore_review.canon_id("item", "Ashen Fang", {"item:ashen-fang"}) == "item:ashen-fang-2"
    approved = {"npc:tamsin-reed": {"entry_id": "gm:c:tamsin-reed", "family": "person", "name": "Tamsin Reed",
                                    "row": {"name": "Tamsin Reed", "location_id": VILLAGE},
                                    "play": {"schedule": [{"from_hour": 0, "to_hour": 24, "location_id": VILLAGE}]}},
                "quest:ferry-word": {"entry_id": "gm:c:ferry-word", "family": "quest", "name": "Ferry Word",
                                     "row": {"giver_id": "gm:c:tamsin-reed", "steps": []}, "play": {}}}
    canon, topology = lore_review.with_approved_inventions({"entities": []}, {}, approved)
    entities = {row["id"]: row for row in canon["entities"]}
    assert entities["npc:tamsin-reed"]["kind"] == "character" and entities["quest:ferry-word"]["giver_id"] == "npc:tamsin-reed"
    assert canon["routines"] == [{"npc_id": "npc:tamsin-reed", "schedule": approved["npc:tamsin-reed"]["play"]["schedule"]}]


def test_version_15_brings_an_empty_lore_layer() -> None:
    assert _document()["simulation_state"]["lore_layer"] == {"entries": {}}
    assert c.InventionAdded(entry_id="gm:c:x", family="item", name="X").type == "invention_added"


def test_every_number_of_an_invented_item_sits_inside_its_slots_budget() -> None:
    """Review: a ring that hit for 60, or a blade whose least damage passed its most, folded in."""
    def item(slot: str, stats: dict) -> str:
        return fold_invention(_document(), {"family": "item", "name": f"Odd {slot}", "play": {
            "type": "gear", "equipment": {"slot": slot, "stats": stats}, "location_id": GROVE}}).refused
    assert item("ring", {"damage_min": 40, "damage_max": 60}) == "what is worn as ring does no damage"
    assert item("main_hand", {"damage_min": 50, "damage_max": 4}) == "its least damage is more than its most"
    assert item("main_hand", {"damage_max": 4, "accuracy_bonus": 30}).startswith("its bonus is outside")
    assert item("ring", {"armor": 3}).startswith("its armor is outside")


def test_an_inventions_places_are_places_and_its_quest_can_be_done() -> None:
    """Review: a road to a person made a location of them; an invented quest's steps were in no shape the quest rule
    reads."""
    from app.apps.rpg.rules.quest.progress import step_ways

    road = {"family": "place", "name": "Odd Lane", "play": {"roads": [{"to": "npc:orik-stonewake"}]}}
    assert fold_invention(_document(), road).refused.startswith("a place joins the roads")
    quest = {"family": "quest", "name": "The Lost Ledger", "play": {"giver_id": "npc:orik-stonewake", "steps": [
        {"summary": "Find it", "conditions": [{"kind": "reach", "subject": VILLAGE}]}], "reward": {"xp": 60, "copper": 100}}}
    document, made = _played(_document(), quest)
    step = document["simulation_state"]["world_model"]["quests"][made[0].entry_id]["steps"][0]
    assert step_ways(step)[0][0] == [{"reach": VILLAGE}]


def test_a_game_master_never_sets_an_authored_outcome_or_a_fact_again() -> None:
    from app.apps.rpg.rules.consequences import fold_fact

    document = _document()
    document["simulation_state"]["world_model"]["fact_effects"] = [
        {"when": {"engine_fate": "guild"}, "place": {"location": VILLAGE, "line": "Guild banners hang."}}]
    assert fold_fact(document, {"fact": "engine_fate", "value": "guild"}).refused.endswith("left to the hero")
