from __future__ import annotations

from typing import Dict


SERVICE_PRICES: Dict[str, Dict[str, Dict[str, int]]] = {
    "inn": {
        "common_room": {"silver": 8},
        "private_room": {"silver": 2},
        "meal": {"copper": 3},
        "ale": {"copper": 5},
    },
    "travel": {
        "local_passage": {"silver": 5},
        "guarded_passage": {"gold": 1, "silver": 5},
    },
    "repair": {
        "basic_repair": {"silver": 6},
        "armor_repair": {"gold": 1},
        "weapon_repair": {"silver": 8},
    },
}


ITEM_PRICES: Dict[str, Dict[str, int]] = {
    "torch": {"silver": 1},
    "rope": {"silver": 3},
    "dagger": {"silver": 8},
    "iron_sword": {"gold": 1, "silver": 5},
    "short_bow": {"gold": 1, "silver": 2},
    "health_potion": {"gold": 3},
    "bread": {"copper": 2},
    "waterskin": {"silver": 4},
}
