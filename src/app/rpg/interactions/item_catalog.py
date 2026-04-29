from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

ITEM_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "def:rusty_key": {
        "definition_id": "def:rusty_key",
        "name": "rusty key",
        "kind": "key",
        "stackable": False,
        "max_stack": 1,
        "unit_weight": 0.05,
        "rarity": "common",
        "value": {"gold": 0, "silver": 0, "copper": 5},
        "tags": ["key"],
    },
    "def:rusty_dagger": {
        "definition_id": "def:rusty_dagger",
        "name": "rusty dagger",
        "kind": "weapon",
        "stackable": False,
        "max_stack": 1,
        "unit_weight": 1.2,
        "rarity": "common",
        "value": {"gold": 0, "silver": 8, "copper": 0},
        "tags": ["weapon", "blade", "dagger"],
        "equipment": {
            "slot": "main_hand",
            "stats": {
                "damage_min": 1,
                "damage_max": 4,
                "accuracy_bonus": 0,
            },
        },
        "condition": {
            "durability": 0.55,
            "max_durability": 1.0,
        },
    },
    "def:small_knife": {
        "definition_id": "def:small_knife",
        "name": "small knife",
        "kind": "weapon",
        "stackable": False,
        "max_stack": 1,
        "unit_weight": 0.8,
        "rarity": "common",
        "value": {"gold": 0, "silver": 5, "copper": 0},
        "tags": ["weapon", "blade", "knife"],
        "equipment": {
            "slot": "main_hand",
            "stats": {
                "damage_min": 1,
                "damage_max": 3,
                "accuracy_bonus": 1,
            },
        },
        "condition": {
            "durability": 0.8,
            "max_durability": 1.0,
        },
    },
    "def:rope": {
        "definition_id": "def:rope",
        "name": "rope",
        "kind": "tool",
        "stackable": False,
        "max_stack": 1,
        "unit_weight": 2.0,
        "rarity": "common",
        "value": {"gold": 0, "silver": 2, "copper": 0},
        "tags": ["tool", "rope"],
    },
    "def:iron_arrow": {
        "definition_id": "def:iron_arrow",
        "name": "iron arrow",
        "kind": "ammo",
        "stackable": True,
        "max_stack": 99,
        "unit_weight": 0.05,
        "rarity": "common",
        "value": {"gold": 0, "silver": 0, "copper": 2},
        "tags": ["ammo", "arrow", "piercing"],
    },
    "def:heavy_anvil": {
        "definition_id": "def:heavy_anvil",
        "name": "heavy anvil",
        "kind": "tool",
        "stackable": False,
        "max_stack": 1,
        "unit_weight": 65.0,
        "rarity": "uncommon",
        "value": {"gold": 2, "silver": 5, "copper": 0},
        "tags": ["tool", "smithing", "heavy"],
    },
}


NAME_TO_DEFINITION_ID = {
    "rusty key": "def:rusty_key",
    "key": "def:rusty_key",
    "rusty dagger": "def:rusty_dagger",
    "dagger": "def:rusty_dagger",
    "small knife": "def:small_knife",
    "knife": "def:small_knife",
    "rope": "def:rope",
    "length of rope": "def:rope",
    "iron arrow": "def:iron_arrow",
    "iron arrows": "def:iron_arrow",
    "arrow": "def:iron_arrow",
    "arrows": "def:iron_arrow",
    "heavy anvil": "def:heavy_anvil",
    "anvil": "def:heavy_anvil",
}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _norm(value: Any) -> str:
    return _safe_str(value).strip().lower()


def get_item_definition(definition_id: str) -> Dict[str, Any]:
    return deepcopy(ITEM_DEFINITIONS.get(_safe_str(definition_id), {}))


def infer_definition_id_from_name(name: str) -> str:
    return NAME_TO_DEFINITION_ID.get(_norm(name), "")


def definition_for_item_like(item: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(item, dict):
        return {}

    definition_id = _safe_str(item.get("definition_id"))
    if definition_id:
        found = get_item_definition(definition_id)
        if found:
            return found

    name = _safe_str(item.get("name") or item.get("title") or item.get("label"))
    inferred = infer_definition_id_from_name(name)
    if inferred:
        return get_item_definition(inferred)

    item_id = _safe_str(item.get("item_id") or item.get("id") or item.get("entity_id"))
    clean_id = item_id.replace("item:", "").replace("_", " ")
    inferred = infer_definition_id_from_name(clean_id)
    if inferred:
        return get_item_definition(inferred)

    return {}
