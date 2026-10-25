"""Campaign documents upcast from v5: one inventory, no creation artifacts, every campaign bound (RQ-1.1, v6),
and a starter town campaign playing from the starter world (RQ-2.8, v7).

The fixtures are real v5 documents, written by the v5 code two turns into a campaign: the starter town, the
demo, a World Forge (genesis) new game, Aurelia and Vesper-9. (Vesper-9's campaign bible projection and the
genesis artifacts are trimmed to keep the fixtures small; nothing the upcaster reads.)
"""
from __future__ import annotations

import gzip
import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.apps.rpg.foundation.state import SECTION_PATHS, CampaignStateView, read_path
from app.apps.rpg.genesis.worlds.builtin_worlds import STARTER, installed_world_id, legacy_ids
from app.apps.rpg.session.campaign_state import (
    CREATION_ARTIFACT_PATHS,
    CURRENT_SCHEMA_VERSION,
    CampaignState,
    merge_inventories,
    split_creation_artifacts,
    upcast_campaign_document,
    upcast_if_outdated,
)

FIXTURES = Path(__file__).resolve().parents[2] / "rpg" / "fixtures" / "campaign_documents_v5"
SHAPES = ("starter", "demo", "genesis", "aurelia", "vesper")
BINDING = {"starter": "starter", "demo": "demo", "genesis": "genesis", "aurelia": "published", "vesper": "published"}


def _v5(shape: str) -> dict:
    return json.loads(gzip.decompress((FIXTURES / f"{shape}.json.gz").read_bytes()))


def _facts(document: dict) -> dict:
    view = CampaignStateView(document)
    return {
        "name": view.player.name,
        "hp": view.player.hp,
        "level": view.player.level,
        "purse": view.inventory.purse.total_copper if view.inventory.purse else None,
        "inventory": sorted((item.name, item.quantity) for item in view.inventory.items),
        "location": view.location.location_id,
        "quests": sorted((quest.title, quest.status) for quest in view.quests.quests),
        "party": [companion.npc_id for companion in view.party.companions],
        "survival": (view.survival.hunger, view.survival.thirst, view.survival.fatigue),
        "tick": view.time.tick,
    }


def _size(document: dict) -> int:
    return len(json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode())


@pytest.mark.parametrize("shape", SHAPES)
def test_every_campaign_shape_upcasts_validates_and_round_trips(shape: str) -> None:
    v5 = _v5(shape)
    assert v5["manifest"]["schema_version"] == 5
    v6 = upcast_campaign_document(deepcopy(v5))

    assert v6["manifest"]["schema_version"] == CURRENT_SCHEMA_VERSION == 10
    CampaignState.model_validate(v6)
    CampaignStateView(v6).validate()  # every section reads
    expected = _facts(v5)
    if shape == "starter":  # the starter world names its places by its own ids
        expected["location"] = legacy_ids(STARTER).get(expected["location"], expected["location"])
    assert _facts(v6) == expected  # the upgrade changes no fact a player can check
    assert "simulation_state" not in v6["setup_payload"].get("metadata", {})
    assert CampaignStateView(v6).world.binding_kind == BINDING[shape]
    if shape == "starter":
        assert v6["state"]["world_binding"]["world_id"] == installed_world_id(STARTER)
    elif BINDING[shape] != "published":
        assert v6["state"]["world_binding"] == {"kind": BINDING[shape]}

    stored = json.loads(json.dumps(v6))  # what PostgreSQL stores and returns
    assert upcast_if_outdated(stored) is stored  # a v6 document loads as stored
    assert upcast_campaign_document(deepcopy(stored)) == stored  # and upcasting it again changes nothing


@pytest.mark.parametrize("shape", SHAPES)
def test_the_sheet_inventory_and_every_purse_agree_with_the_store(shape: str) -> None:
    v6 = upcast_campaign_document(_v5(shape))
    store = v6["simulation_state"]["player_state"].get("inventory_state") or {}
    if not isinstance(store.get("items"), list):
        pytest.skip(f"{shape}: no simulation store yet")
    sheet = v6["state"]["player"]
    assert [(item["name"], item["quantity"]) for item in sheet["inventory"]] == [
        (item["name"], item.get("quantity", item.get("qty"))) for item in store["items"]]
    assert sheet["currency"] == store["currency"] == v6["simulation_state"]["player_state"]["currency"]


def test_a_diverged_inventory_merges_with_the_store_winning_and_lists_what_changed() -> None:
    """The starter town's absent-merchant purchase left the store's purse at 100 while the turns' purse and
    the sheet said 0, and the sheet listed a potion the store never received (roadmap Q-2)."""
    document = _v5("starter")
    player_state = document["simulation_state"]["player_state"]
    player_state["currency"] = {"gold": 0, "silver": 0, "copper": 0}
    document["state"]["player"]["currency"] = {"gold": 0, "silver": 0, "copper": 0}
    document["state"]["player"]["inventory"].append({"id": "healing_potion", "name": "Healing Potion", "quantity": 1})
    torch = next(item for item in player_state["inventory_state"]["items"] if item["name"] == "Torch")
    torch["qty"] = 1

    merged, differences = merge_inventories(deepcopy(document))
    assert {"field": "purse", "copy": "simulation_store", "was": 100, "now": 0} in differences
    assert {"field": "inventory", "item": "Healing Potion", "sheet": 1, "simulation": 0} in differences
    assert {"field": "inventory", "item": "Torch", "sheet": 2, "simulation": 1} in differences
    sheet = {item["name"]: item["quantity"] for item in merged["state"]["player"]["inventory"]}
    assert "Healing Potion" not in sheet and sheet["Torch"] == 1
    assert merged["simulation_state"]["player_state"]["inventory_state"]["currency"]["silver"] == 0
    assert merge_inventories(deepcopy(merged))[1] == []  # merged once, nothing left to merge


def test_a_genesis_campaign_keeps_its_creation_artifacts_once_outside_the_document() -> None:
    document = _v5("genesis")
    before = _size(document)
    stored, artifacts = split_creation_artifacts(upcast_campaign_document(deepcopy(document)))
    assert sorted(artifacts) == ["bootstrap_snapshot", "compiled_genesis"]
    assert artifacts["compiled_genesis"] == document["setup_payload"]["compiled_genesis"]
    for paths in CREATION_ARTIFACT_PATHS.values():
        for section, key in paths:
            assert key not in stored[section]
    assert _size(stored) < before


def test_every_section_names_the_paths_it_owns_and_no_path_twice() -> None:
    owners: dict[tuple[str, ...], str] = {}
    for name, paths in SECTION_PATHS.items():
        assert paths, name
        for path in paths:
            assert path not in owners, (path, owners.get(path), name)
            owners[path] = name
    v6 = upcast_campaign_document(_v5("aurelia"))
    assert read_path(v6, ("simulation_state", "player_state", "inventory_state", "items"))


def test_save_package_format_8_carries_a_v6_campaign_document() -> None:
    from app.apps.rpg.foundation.persistence import CURRENT_RPG_SCHEMA_VERSION, build_campaign_save_package
    from app.apps.rpg.foundation.persistence.migration_manager import migrate_package_to_current
    from app.apps.rpg.session.campaign_state import NewerCampaignDocumentError, load_campaign_save_package

    v6 = upcast_campaign_document(_v5("aurelia"))
    package = build_campaign_save_package(v6, now="2026-10-23T00:00:00+00:00")
    assert package["schema_version"] == CURRENT_RPG_SCHEMA_VERSION == 8
    assert package["campaign"]["document_version"] == CURRENT_SCHEMA_VERSION
    assert load_campaign_save_package(json.loads(json.dumps(package))) == json.loads(json.dumps(v6))

    v7 = {key: value for key, value in package.items() if key != "campaign"} | {"schema_version": 7}
    migrated = migrate_package_to_current(v7)
    assert migrated["schema_version"] == 8 and migrated["campaign"] == {"document_version": None, "document": None}
    assert load_campaign_save_package(v7) is None  # a v7 package carries no campaign document

    v5_package = build_campaign_save_package(_v5("starter"))
    assert load_campaign_save_package(v5_package)["manifest"]["schema_version"] == CURRENT_SCHEMA_VERSION  # on load
    newer = deepcopy(package)
    newer["campaign"]["document"]["manifest"]["schema_version"] = CURRENT_SCHEMA_VERSION + 1
    with pytest.raises(NewerCampaignDocumentError):
        load_campaign_save_package(newer)


def test_a_starter_town_campaign_plays_from_the_starter_world() -> None:
    """v7 (RQ-2.8): the places and people the starter town's code named (loc_tavern, npc:Bran) are the world's,
    and the campaign has the world model for where the hero stands, with who is present there."""
    v5 = _v5("starter")
    upgraded = upcast_campaign_document(deepcopy(v5))
    simulation = upgraded["simulation_state"]
    model = simulation["world_model"]
    here = simulation["player_state"]["location_id"]
    assert here in model["locations"] and here.startswith("location:market-road:")
    assert set(simulation["present_npc_state"]["present_npc_ids"]) == {
        npc["id"] for npc in model["locations"][here]["present_npcs"]}
    assert {"npc:bran", "npc:mira", "npc:elara"} <= set(model["npcs"])
    text = json.dumps(upgraded)
    for legacy in ("\"loc_tavern\"", "\"npc:Bran\""):
        assert legacy not in text, legacy


def test_a_world_forge_campaign_is_not_bound_to_the_starter_world() -> None:
    upgraded = upcast_campaign_document(_v5("genesis"))
    assert upgraded["state"]["world_binding"] == {"kind": "genesis"}
    assert "world_model" not in upgraded["simulation_state"] or upgraded["simulation_state"]["world_model"].get(
        "world_id") != installed_world_id(STARTER)
