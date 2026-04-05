"""Phase 9.0 — Deterministic static item registry.

All item definitions are serialisable, no randomness or generated fields.
"""
from __future__ import annotations

from typing import Any, Dict


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


# Deterministic static item registry.
# No randomness, no generated fields, all serialisable.
_ITEM_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "gold_coin": {
        "item_id": "gold_coin",
        "name": "Gold Coin",
        "category": "currency",
        "stackable": True,
        "max_stack": 9999,
        "tags": ["currency"],
    },
    "healing_potion": {
        "item_id": "healing_potion",
        "name": "Healing Potion",
        "category": "consumable",
        "stackable": True,
        "max_stack": 10,
        "tags": ["consumable", "healing"],
        "effect": {
            "type": "restore_resource",
            "resource": "health",
            "amount": 10,
        },
    },
    "bandit_token": {
        "item_id": "bandit_token",
        "name": "Bandit Token",
        "category": "quest",
        "stackable": True,
        "max_stack": 20,
        "tags": ["quest", "proof"],
    },
}


def get_item_definition(item_id: str) -> Dict[str, Any]:
    """Return a copy of the item definition for *item_id*, or an empty dict."""
    item_id = str(item_id or "")
    return _safe_dict(_ITEM_DEFINITIONS.get(item_id))


def list_item_definitions() -> Dict[str, Dict[str, Any]]:
    """Return a sorted copy of every item definition, keyed by item_id."""
    return {
        str(item_id): _safe_dict(item_def)
        for item_id, item_def in sorted(_ITEM_DEFINITIONS.items(), key=lambda kv: str(kv[0]))
    }