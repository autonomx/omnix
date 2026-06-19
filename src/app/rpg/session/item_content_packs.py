"""Deterministic RPG item content packs.

This module expands item-system content without changing the core catalog contract.
Content packs are engine-owned: mechanics, ids, prices, recipe ids, and tags are
fixed here, while future AI fiction generation may only decorate safe display
fields through the item-description boundary.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .item_system import build_item_catalog, normalize_item_instance

CONTENT_PACK_IDS = ("starter_survival", "field_crafting", "merchant_basics")

_STARTER_SURVIVAL_ITEMS: dict[str, dict[str, Any]] = {
    "bandage_roll": {
        "id": "bandage_roll",
        "item_id": "bandage_roll",
        "name": "Bandage roll",
        "type": "consumable",
        "item_type": "consumable",
        "consumable_type": "healing",
        "quantity": 1,
        "stackable": True,
        "rarity": "common",
        "level": 1,
        "item_level": 1,
        "effects": [{"op": "restore_resource", "resource": "hp", "amount": 8, "dimension": "resources"}],
        "tags": ["healing", "field_care", "starter_survival"],
        "value": 3,
        "weight": 0.1,
    },
    "campfire_kit": {
        "id": "campfire_kit",
        "item_id": "campfire_kit",
        "name": "Campfire kit",
        "type": "tool",
        "item_type": "tool",
        "quantity": 1,
        "stackable": False,
        "rarity": "common",
        "level": 1,
        "item_level": 1,
        "effects": [{"op": "apply_scene_status", "status": "campfire_lit", "dimension": "environment"}],
        "tags": ["camping", "light", "rest", "starter_survival"],
        "value": 5,
        "weight": 1.0,
    },
    "trail_marker_chalk": {
        "id": "trail_marker_chalk",
        "item_id": "trail_marker_chalk",
        "name": "Trail marker chalk",
        "type": "tool",
        "item_type": "tool",
        "quantity": 1,
        "stackable": True,
        "rarity": "common",
        "level": 1,
        "item_level": 1,
        "effects": [{"op": "add_affordance", "affordance": "marked_return_path", "dimension": "position"}],
        "tags": ["navigation", "travel", "starter_survival"],
        "value": 1,
        "weight": 0.1,
    },
}

_FIELD_CRAFTING_RECIPES: dict[str, dict[str, Any]] = {
    "recipe_bandage_roll": {
        "recipe_id": "recipe_bandage_roll",
        "name": "Craft bandage roll",
        "output_item_id": "bandage_roll",
        "output_quantity": 1,
        "ingredients": [{"item_id": "leather_strip", "quantity": 1}, {"item_id": "keenleaf", "quantity": 1}],
        "station": "field",
        "tags": ["healing", "field_crafting"],
    },
    "recipe_campfire_kit": {
        "recipe_id": "recipe_campfire_kit",
        "name": "Assemble campfire kit",
        "output_item_id": "campfire_kit",
        "output_quantity": 1,
        "ingredients": [{"item_id": "torch", "quantity": 1}, {"item_id": "rope_coil", "quantity": 1}],
        "station": "field",
        "tags": ["camping", "field_crafting"],
    },
    "recipe_trail_marker_chalk": {
        "recipe_id": "recipe_trail_marker_chalk",
        "name": "Prepare trail marker chalk",
        "output_item_id": "trail_marker_chalk",
        "output_quantity": 2,
        "ingredients": [{"item_id": "focus_crystal", "quantity": 1}],
        "station": "field",
        "tags": ["navigation", "field_crafting"],
    },
}

_MERCHANT_BASICS_PROFILE: dict[str, Any] = {
    "merchant_id": "roadside_supplier",
    "name": "Roadside supplier",
    "stock_item_ids": ["ration", "torch", "waterskin", "bandage_roll", "campfire_kit", "trail_marker_chalk"],
    "buy_markup": 1.15,
    "sell_markdown": 0.55,
    "tags": ["travel", "survival", "merchant_basics"],
}


def build_item_content_pack(pack_id: str, *, genre: str = "classic_fantasy", level: int = 1) -> dict[str, Any]:
    """Build one deterministic item content pack by id."""

    catalog = build_item_catalog(genre=genre, level=level)
    if pack_id == "starter_survival":
        return {
            "pack_id": pack_id,
            "items": _content_items(catalog),
            "recipes": {},
            "merchant_profiles": {},
        }
    if pack_id == "field_crafting":
        return {
            "pack_id": pack_id,
            "items": _content_items(catalog),
            "recipes": deepcopy(_FIELD_CRAFTING_RECIPES),
            "merchant_profiles": {},
        }
    if pack_id == "merchant_basics":
        return {
            "pack_id": pack_id,
            "items": _content_items(catalog),
            "recipes": {},
            "merchant_profiles": {"roadside_supplier": deepcopy(_MERCHANT_BASICS_PROFILE)},
        }
    return {"pack_id": pack_id, "items": {}, "recipes": {}, "merchant_profiles": {}, "warnings": ["unknown_content_pack"]}


def build_item_content_bundle(pack_ids: list[str] | tuple[str, ...] = CONTENT_PACK_IDS, *, genre: str = "classic_fantasy", level: int = 1) -> dict[str, Any]:
    """Merge deterministic item content packs into one bundle."""

    merged = {"pack_ids": list(pack_ids), "items": {}, "recipes": {}, "merchant_profiles": {}, "warnings": []}
    for pack_id in pack_ids:
        pack = build_item_content_pack(pack_id, genre=genre, level=level)
        merged["items"].update(deepcopy(pack.get("items", {})))
        merged["recipes"].update(deepcopy(pack.get("recipes", {})))
        merged["merchant_profiles"].update(deepcopy(pack.get("merchant_profiles", {})))
        merged["warnings"].extend(pack.get("warnings", []))
    return merged


def _content_items(catalog: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    items = {item_id: normalize_item_instance(item) for item_id, item in _STARTER_SURVIVAL_ITEMS.items()}
    items.update({item_id: deepcopy(catalog[item_id]) for item_id in ("ration", "torch", "waterskin", "rope_coil", "keenleaf", "leather_strip", "focus_crystal") if item_id in catalog})
    return items
