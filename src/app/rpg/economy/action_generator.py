from __future__ import annotations

from typing import Any, Dict

from app.rpg.economy.transactions import enrich_action_with_registry_price


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def build_menu_action(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(payload)

    action = {
        "action_type": _safe_str(payload.get("action_type")),
    }

    for key in (
        "item_id",
        "quantity",
        "service_type",
        "service_id",
        "target_id",
        "repair_item_id",
        "provider_id",
        "provider_name",
    ):
        if payload.get(key) is not None:
            action[key] = payload.get(key)

    action["apply_cost"] = True
    return enrich_action_with_registry_price(action)
