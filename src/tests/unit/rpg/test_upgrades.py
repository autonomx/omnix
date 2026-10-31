"""Upgrades (evolution roadmap EV-5): a seller improves a carried piece of gear by one tier, for materials and coin, up
to the recipe's last tier and inside the hero's level's budget for its slot."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from app.apps.rpg.foundation.state import changes as c
from app.apps.rpg.foundation.state.reducer import reduce
from app.apps.rpg.rules.economy.trade import buy
from app.apps.rpg.session.campaign_state import upcast_campaign_document

FIXTURE = Path(__file__).resolve().parents[2] / "rpg" / "fixtures" / "campaign_documents_v5" / "aurelia.json.gz"
SMITH, HERE = "npc:orik-stonewake", "location:aurelia:starfall-village"
OFFER = f"{SMITH}:improve"


def _document(level: int = 5) -> dict:
    document = upcast_campaign_document(json.loads(gzip.decompress(FIXTURE.read_bytes())))
    document, _ = reduce(document, [
        c.LocationChanged(location_id=HERE, location_name="Starfall Village"),
        c.PresenceChanged(location_id=HERE, present_npc_ids=(SMITH,)),
        c.ItemAdded(item_id="item:test-blade", name="Test Blade", category="weapon",
                    fields={"equipment": {"slot": "main_hand", "stats": {"damage_min": 2, "damage_max": 6}}}),
        c.ItemEquipped(slot="main_hand", item_id="item:test-blade"),  # the one wielded, over the carried dagger
        c.ItemAdded(item_id="item:aether-shard", name="Aether Shard", quantity=3, category="material"),
        c.PurseChanged(delta_copper=5000)])
    simulation = document["simulation_state"]
    simulation["player_state"]["level"] = level
    simulation["world_model"]["offers"][SMITH].append({
        "offer_id": OFFER, "service_kind": "upgrade", "provider_id": SMITH, "label": "Improve a blade",
        "price": {"gold": 0, "silver": 6, "copper": 0}, "availability": "available",
        "recipe": {"slots": ["main_hand"], "materials": [{"item_id": "item:aether-shard", "quantity": 2}],
                   "per_tier": {"damage_max": 1}, "max_tier": 2}})
    return document


def _blade(document: dict) -> dict:
    items = document["simulation_state"]["player_state"]["inventory_state"]["items"]
    return next(row for row in items if row["item_id"] == "item:test-blade")


def test_a_blade_is_improved_by_a_tier_for_its_materials_and_coin() -> None:
    document = _document()
    done = buy(document["simulation_state"], OFFER, SMITH)
    assert not done.refused, done.lines
    line = done.lines[0]  # priced as the seller prices (a region's or seller's factor), by the tier
    assert line.startswith("Orik Stonewake works on your Test Blade for ") and line.endswith(
        ": it is tier 1 now (damage max 6 to 7).")
    after, _ = reduce(document, done.changes)
    assert _blade(after)["tier"] == 1 and _blade(after)["equipment"]["stats"]["damage_max"] == 7
    shards = next(row for row in after["simulation_state"]["player_state"]["inventory_state"]["items"]
                  if row["item_id"] == "item:aether-shard")
    assert shards["qty"] == 1
    again = buy(after["simulation_state"], "item:test-blade", SMITH)  # naming the blade finds who improves it
    assert again.refused and again.lines == ["Orik Stonewake needs 2 × Aether Shard for that."]


def test_no_tier_beyond_the_recipe_or_the_levels_budget() -> None:
    low = buy(_document(level=1)["simulation_state"], OFFER, SMITH)
    assert low.refused and low.lines == ["The Test Blade is as good as a hero of your level can make use of."]
    document = _document()
    document, _ = reduce(document, [c.ItemImproved(item_id="item:test-blade", tier=2, stats={"damage_max": 8})])
    top = buy(document["simulation_state"], "item:test-blade", SMITH)  # named: unnamed, the dagger would be chosen
    assert top.refused and top.lines == ["The Test Blade can be improved no further."]


def test_a_worlds_own_weapon_is_improved_as_the_kind_it_fights_as() -> None:
    # "Iron Dagger" carries no equipment block: it fights as a dagger, and is improved as one, the block written.
    document = _document()
    document, _ = reduce(document, [c.ItemEquipped(slot="main_hand", item_id="iron_dagger")])
    done = buy(document["simulation_state"], OFFER, SMITH)  # the wielded weapon, improved
    assert not done.refused and done.lines[0].endswith(": it is tier 1 now (damage max 4 to 5).")
    after, _ = reduce(document, done.changes)
    dagger = next(row for row in after["simulation_state"]["player_state"]["inventory_state"]["items"]
                  if row["item_id"] == "iron_dagger")
    assert dagger["tier"] == 1 and dagger["equipment"] == {
        "slot": "main_hand", "stats": {"damage_min": 1, "damage_max": 5, "accuracy_bonus": 0}}


def test_unnamed_the_piece_that_can_still_be_improved_and_a_block_with_no_slot_gets_one() -> None:
    document = _document()
    document, _ = reduce(document, [c.ItemImproved(item_id="item:test-blade", tier=2, stats={"damage_max": 8})])
    done = buy(document["simulation_state"], OFFER, SMITH)  # the wielded blade is at its last tier: the dagger
    assert not done.refused and "Iron Dagger" in done.lines[0]
    document, _ = reduce(document, [c.ItemAdded(item_id="item:bare", name="Bare Blade", category="weapon",
                                                fields={"equipment": {"stats": {"damage_max": 3}}})])
    after, _ = reduce(document, [c.ItemImproved(item_id="item:bare", tier=1, stats={"damage_max": 4}, slot="main_hand")])
    bare = next(row for row in after["simulation_state"]["player_state"]["inventory_state"]["items"]
                if row["item_id"] == "item:bare")
    assert bare["equipment"] == {"stats": {"damage_max": 4}, "slot": "main_hand"}
