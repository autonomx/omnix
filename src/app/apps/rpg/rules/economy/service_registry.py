from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Dict, List
from app.apps.rpg.foundation.safe_values import safe_list as _safe_list, safe_str as _safe_str

SERVICE_KIND_LODGING = "lodging"
SERVICE_KIND_MEAL = "meal"
SERVICE_KIND_DRINK = "drink"
SERVICE_KIND_SHOP_GOODS = "shop_goods"
SERVICE_KIND_HEALING = "healing"
SERVICE_KIND_TRAINING = "training"
SERVICE_KIND_REPAIR = "repair"
SERVICE_KIND_TRANSPORT = "transport"
SERVICE_KIND_PAID_INFORMATION = "paid_information"


SERVICE_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "npc:Bran": {
        "provider_id": "npc:Bran",
        "provider_name": "Bran",
        "aliases": ["bran", "innkeeper", "bran the innkeeper"],
        "location_id": "loc_tavern",
        "service_kinds": [
            SERVICE_KIND_LODGING,
            SERVICE_KIND_MEAL,
            SERVICE_KIND_DRINK,
            SERVICE_KIND_PAID_INFORMATION,
        ],
    },
    "npc:Elara": {
        "provider_id": "npc:Elara",
        "provider_name": "Elara",
        "aliases": ["elara", "merchant", "elara the merchant"],
        "location_id": "loc_market",
        "service_kinds": [
            SERVICE_KIND_SHOP_GOODS,
            SERVICE_KIND_REPAIR,
            SERVICE_KIND_PAID_INFORMATION,
        ],
    },
}


SERVICE_OFFERS: Dict[str, List[Dict[str, Any]]] = {
    "npc:Bran": [
        {
            "offer_id": "bran_lodging_common_cot",
            "service_kind": SERVICE_KIND_LODGING,
            "provider_id": "npc:Bran",
            "provider_name": "Bran",
            "label": "Common room cot",
            "description": "A simple cot in the common room for one night.",
            "price": {"gold": 0, "silver": 5, "copper": 0},
            "stock": 6,
            "availability_rules": {
                "requires_provider_present": True,
                "requires_location": "loc_tavern",
            },
            "availability": "available",
            "effects": {
                "lodging_reserved": True,
                "rest_quality": "basic",
                "duration": "one_night",
            },
        },
        {
            "offer_id": "bran_lodging_private_room",
            "service_kind": SERVICE_KIND_LODGING,
            "provider_id": "npc:Bran",
            "provider_name": "Bran",
            "label": "Private room",
            "description": "A private room for one night.",
            "price": {"gold": 1, "silver": 0, "copper": 0},
            "stock": 1,
            "availability_rules": {
                "requires_provider_present": True,
                "requires_location": "loc_tavern",
            },
            "availability": "available",
            "effects": {
                "lodging_reserved": True,
                "rest_quality": "good",
                "duration": "one_night",
            },
        },
        {
            "offer_id": "bran_meal_stew",
            "service_kind": SERVICE_KIND_MEAL,
            "provider_id": "npc:Bran",
            "provider_name": "Bran",
            "label": "Hot stew",
            "description": "A hot bowl of stew and bread.",
            "price": {"gold": 0, "silver": 1, "copper": 5},
            "availability_rules": {
                "requires_provider_present": True,
                "requires_location": "loc_tavern",
            },
            "availability": "available",
            "effects": {
                "meal_consumed": True,
                "morale": 1,
            },
        },
        {
            "offer_id": "bran_dried_rations",
            "service_kind": SERVICE_KIND_MEAL,
            "provider_id": "npc:Bran",
            "provider_name": "Bran",
            "label": "Dried rations",
            "description": "A wrapped packet of dried meat, hard cheese, and preserved berries.",
            "price": {"gold": 0, "silver": 5, "copper": 0},
            "stock": 4,
            "availability_rules": {
                "requires_provider_present": True,
                "requires_location": "loc_tavern",
            },
            "availability": "available",
            "effects": {
                "items_added": [
                    {
                        "item_id": "dried_rations",
                        "name": "Dried rations",
                        "quantity": 1,
                        "type": "food",
                    }
                ],
            },
        },
        {
            "offer_id": "bran_drink_ale",
            "service_kind": SERVICE_KIND_DRINK,
            "provider_id": "npc:Bran",
            "provider_name": "Bran",
            "label": "Mug of ale",
            "description": "A mug of local ale.",
            "price": {"gold": 0, "silver": 0, "copper": 8},
            "availability_rules": {
                "requires_provider_present": True,
                "requires_location": "loc_tavern",
            },
            "availability": "available",
            "effects": {
                "drink_consumed": True,
            },
        },
        {
            "offer_id": "bran_paid_rumor",
            "service_kind": SERVICE_KIND_PAID_INFORMATION,
            "provider_id": "npc:Bran",
            "provider_name": "Bran",
            "label": "Local rumor",
            "description": "A useful rumor from tavern gossip.",
            "price": {"gold": 0, "silver": 2, "copper": 0},
            "availability_rules": {
                "requires_provider_present": True,
                "requires_location": "loc_tavern",
            },
            "availability": "available",
            "effects": {
                "rumor_added": True,
            },
        },
    ],
    "npc:Elara": [
        {
            "offer_id": "elara_torch",
            "service_kind": SERVICE_KIND_SHOP_GOODS,
            "provider_id": "npc:Elara",
            "provider_name": "Elara",
            "label": "Torch",
            "description": "A simple torch for dark places.",
            "price": {"gold": 0, "silver": 1, "copper": 0},
            "stock": 3,
            "availability_rules": {
                "requires_provider_present": True,
                "requires_location": "loc_market",
            },
            "availability": "available",
            "effects": {
                "items_added": [
                    {
                        "item_id": "torch",
                        "name": "Torch",
                        "quantity": 1,
                    }
                ],
            },
        },
        {
            "offer_id": "elara_rope",
            "service_kind": SERVICE_KIND_SHOP_GOODS,
            "provider_id": "npc:Elara",
            "provider_name": "Elara",
            "label": "Rope",
            "description": "Fifty feet of sturdy hemp rope.",
            "price": {"gold": 0, "silver": 3, "copper": 0},
            "stock": 2,
            "availability_rules": {
                "requires_provider_present": True,
                "requires_location": "loc_market",
            },
            "availability": "available",
            "effects": {
                "items_added": [
                    {
                        "item_id": "rope",
                        "name": "Rope",
                        "quantity": 1,
                    }
                ],
            },
        },
        {
            "offer_id": "elara_paid_information",
            "service_kind": SERVICE_KIND_PAID_INFORMATION,
            "provider_id": "npc:Elara",
            "provider_name": "Elara",
            "label": "Market information",
            "description": "A piece of useful market intelligence.",
            "price": {"gold": 0, "silver": 2, "copper": 0},
            "availability_rules": {
                "requires_provider_present": True,
                "requires_location": "loc_market",
            },
            "availability": "available",
            "effects": {
                "rumor_added": True,
            },
        },
        {
            "offer_id": "elara_basic_repair",
            "service_kind": SERVICE_KIND_REPAIR,
            "provider_id": "npc:Elara",
            "provider_name": "Elara",
            "label": "Basic gear repair",
            "description": "Minor repair work on worn equipment.",
            "price": {"gold": 0, "silver": 4, "copper": 0},
            "availability_rules": {
                "requires_provider_present": True,
                "requires_location": "loc_market",
            },
            "availability": "available",
            "effects": {
                "repair_quality": "basic",
            },
        },
    ],
}


def _world_services(simulation_state: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """A session's own providers and offers (a published world's); ``None`` for the starter town's catalog."""
    world_model = simulation_state.get("world_model") if isinstance(simulation_state, dict) else None
    if not isinstance(world_model, dict) or not world_model.get("locations"):
        return None
    return {"providers": dict(world_model.get("providers") or {}), "offers": dict(world_model.get("offers") or {})}


def service_providers(simulation_state: Dict[str, Any] | None = None) -> Dict[str, Dict[str, Any]]:
    """Every provider the session can trade with: its world's own, or the starter town's."""
    world = _world_services(simulation_state)
    return deepcopy(world["providers"] if world is not None else SERVICE_PROVIDERS)


def get_service_provider(provider_id: str, simulation_state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    world = _world_services(simulation_state)
    catalog = world["providers"] if world is not None else SERVICE_PROVIDERS
    provider = catalog.get(_safe_str(provider_id))
    return deepcopy(provider) if provider else {}


def get_provider_offers(
    provider_id: str,
    service_kind: str = "",
    simulation_state: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    provider_id = _safe_str(provider_id)
    service_kind = _safe_str(service_kind)
    world = _world_services(simulation_state)
    catalog = world["offers"] if world is not None else SERVICE_OFFERS
    offers = []
    for offer in catalog.get(provider_id, []):
        if service_kind and _safe_str(offer.get("service_kind")) != service_kind:
            continue
        offers.append(deepcopy(offer))
    return offers


# What a request asks for, when it names no provider: a room, food, a drink, goods, a repair, news.
_KIND_WORDS = (
    ("lodging", ("room", "rent", "lodging", "bed", "stay", "sleep")),
    ("meal", ("meal", "food", "stew", "bread", "ration", "rations", "provision", "provisions", "eat")),
    ("drink", ("drink", "ale", "wine", "beer")),
    ("shop_goods", ("shop", "buy", "sell", "sells", "merchant", "goods", "supplies", "potion")),
    ("repair", ("repair", "fix", "mend")),
    ("paid_information", ("rumor", "rumour", "news", "information", "register", "registry")),
)


def _find_world_provider(text_l: str, world: Dict[str, Any], simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    from app.apps.rpg.rules.location_registry import current_location_id

    here = current_location_id(simulation_state)
    providers = sorted(world["providers"].values(), key=lambda provider: provider.get("location_id") != here)
    words = set(re.findall(r"[a-z']+", text_l))
    for provider in providers:
        names = [_safe_str(provider.get("provider_name")).lower()]
        names.extend(_safe_str(alias).lower() for alias in _safe_list(provider.get("aliases")))
        if any(name and (name in words or (" " in name and name in text_l)) for name in names):
            return deepcopy(provider)
    for kind, kind_words in _KIND_WORDS:
        if words & set(kind_words):
            for provider in providers:
                if provider.get("location_id") == here and kind in _safe_list(provider.get("service_kinds")):
                    return deepcopy(provider)
    return {}


def find_provider_by_text(text: str, simulation_state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    text_l = _safe_str(text).lower()
    world = _world_services(simulation_state)
    if world is not None:
        return _find_world_provider(text_l, world, simulation_state or {})
    for provider in SERVICE_PROVIDERS.values():
        aliases = [_safe_str(provider.get("provider_name")).lower()]
        aliases.extend(_safe_str(alias).lower() for alias in _safe_list(provider.get("aliases")))
        if any(alias and alias in text_l for alias in aliases):
            return deepcopy(provider)

    # Useful defaults for current starter world.
    if any(word in text_l for word in ("room", "rent", "lodging", "bed", "stay", "meal", "food", "stew", "bread", "ration", "rations", "provision", "provisions", "drink", "ale", "rumor", "rumour")):
        return deepcopy(SERVICE_PROVIDERS["npc:Bran"])
    if any(word in text_l for word in ("shop", "buy", "sell", "sells", "merchant", "goods", "torch", "rope", "repair")):
        return deepcopy(SERVICE_PROVIDERS["npc:Elara"])

    return {}
