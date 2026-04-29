from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

MERCHANTS: Dict[str, Dict[str, Any]] = {
    "npc:Elara": {
        "merchant_id": "npc:Elara",
        "name": "Elara",
        "buy_price_multiplier": 1.0,
        "sell_price_multiplier": 0.5,
        "inventory": {
            "items": [
                {
                    "item_id": "merchant:elara:minor_healing_potion",
                    "definition_id": "def:minor_healing_potion",
                    "quantity": 5,
                    "price_multiplier": 1.0,
                },
                {
                    "item_id": "merchant:elara:oil_flask",
                    "definition_id": "def:oil_flask",
                    "quantity": 3,
                    "price_multiplier": 1.0,
                },
                {
                    "item_id": "merchant:elara:rope",
                    "definition_id": "def:rope",
                    "quantity": 2,
                    "price_multiplier": 1.0,
                },
            ]
        },
        "source": "deterministic_merchant_catalog",
    },
}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def get_default_merchant(merchant_id: str) -> Dict[str, Any]:
    return deepcopy(MERCHANTS.get(_safe_str(merchant_id), {}))
