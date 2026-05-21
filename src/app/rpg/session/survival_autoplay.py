from __future__ import annotations

"""N124 survival-aware autoplay, balance, supply, and advisory gates.

This module is intentionally deterministic and LLM-independent.  It consumes the
survival state/suggestions produced by N123 and returns policy decisions,
metrics, synthetic balance reports, starter/supply helpers, and advisory
readiness gates that autoplay/report layers can attach without changing the live
simulation authority model.
"""

from copy import deepcopy
from typing import Any, Dict, Iterable, List

from app.rpg.economy.currency import can_afford, get_player_currency, normalize_currency
from app.rpg.economy.service_registry import (
    SERVICE_KIND_DRINK,
    SERVICE_KIND_LODGING,
    SERVICE_KIND_MEAL,
    SERVICE_KIND_SHOP_GOODS,
    get_provider_offers,
)
from app.rpg.session.survival_actions import build_survival_suggested_actions

SURVIVAL_BALANCE_CONFIG: Dict[str, Any] = {
    "format_version": "n124_survival_balance_config_v1",
    "pressure_threshold": 50,
    "warning_threshold": 70,
    "severe_threshold": 85,
    "critical_threshold": 95,
    "per_turn_deltas": {"hunger": 1, "thirst": 2, "fatigue": 1},
    "relief_amounts": {
        "eat_food": {"hunger": 30},
        "drink_water": {"thirst": 30},
        "rest": {"fatigue": 25},
        "buy_meal": {"hunger": 35},
        "buy_drink": {"thirst": 30},
        "buy_lodging": {"fatigue": 55},
    },
    "autoplay_priority": [
        "drink_water",
        "eat_food",
        "rest",
        "buy_drink",
        "buy_meal",
        "buy_lodging",
    ],
    "advisory_thresholds": {
        "max_high_pressure_unanswered_turns": 5,
        "max_blocked_relief_loop_count": 3,
        "min_taken_rate_when_suggestions_seen": 0.20,
    },
    "starter_supply": {
        "items": [
            {"item_id": "trail_ration", "name": "Trail ration", "quantity": 3, "tags": ["food", "ration", "survival"]},
            {"item_id": "waterskin", "name": "Waterskin", "quantity": 2, "tags": ["drink", "water", "survival"]},
        ],
        "currency": {"gold": 2, "silver": 10, "copper": 10},
    },
}

SURVIVAL_SHOP_SUPPLIES: Dict[str, List[Dict[str, Any]]] = {
    "npc:Elara": [
        {
            "offer_id": "elara_trail_ration",
            "service_kind": SERVICE_KIND_SHOP_GOODS,
            "provider_id": "npc:Elara",
            "provider_name": "Elara",
            "label": "Trail ration",
            "description": "A compact ration suitable for travel.",
            "price": {"gold": 0, "silver": 0, "copper": 8},
            "stock": 8,
            "effects": {"items_added": [{"item_id": "trail_ration", "name": "Trail ration", "quantity": 1, "tags": ["food", "ration", "survival"]}]},
        },
        {
            "offer_id": "elara_filled_waterskin",
            "service_kind": SERVICE_KIND_SHOP_GOODS,
            "provider_id": "npc:Elara",
            "provider_name": "Elara",
            "label": "Filled waterskin",
            "description": "A filled waterskin for the road.",
            "price": {"gold": 0, "silver": 1, "copper": 0},
            "stock": 5,
            "effects": {"items_added": [{"item_id": "waterskin", "name": "Waterskin", "quantity": 1, "tags": ["drink", "water", "survival"]}]},
        },
    ]
}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _clamp(value: Any, minimum: int = 0, maximum: int = 100) -> int:
    return max(minimum, min(maximum, _safe_int(value, minimum)))


def _item_key(item: Dict[str, Any]) -> str:
    return _safe_str(item.get("item_id") or item.get("id") or item.get("name")).lower()


def _item_qty(item: Dict[str, Any]) -> int:
    return max(0, _safe_int(item.get("quantity", item.get("qty", 1)), 1))


def _item_tags(item: Dict[str, Any]) -> List[str]:
    tags: List[str] = []
    for key in ("tags", "item_tags", "categories"):
        tags.extend(_safe_str(tag).lower() for tag in _safe_list(item.get(key)))
    kind = _safe_str(item.get("kind") or item.get("type") or item.get("category")).lower()
    if kind:
        tags.append(kind)
    return tags


def _is_food(item: Dict[str, Any]) -> bool:
    text = " ".join([_item_key(item), _safe_str(item.get("name")).lower()] + _item_tags(item))
    return any(token in text for token in ("food", "ration", "meal", "bread", "stew"))


def _is_drink(item: Dict[str, Any]) -> bool:
    text = " ".join([_item_key(item), _safe_str(item.get("name")).lower()] + _item_tags(item))
    return any(token in text for token in ("drink", "water", "waterskin", "canteen"))


def _player_state(state: Dict[str, Any]) -> Dict[str, Any]:
    state = _safe_dict(state)
    player_state = state.get("player_state") if isinstance(state.get("player_state"), dict) else {}
    state["player_state"] = player_state
    return player_state


def _inventory_state(state: Dict[str, Any]) -> Dict[str, Any]:
    player_state = _player_state(state)
    inventory = player_state.get("inventory_state") if isinstance(player_state.get("inventory_state"), dict) else {}
    player_state["inventory_state"] = inventory
    inventory.setdefault("items", [])
    inventory.setdefault("currency", normalize_currency(inventory.get("currency")))
    return inventory


def _needs_from_state(state: Dict[str, Any]) -> Dict[str, int]:
    state = _safe_dict(state)
    climate = _safe_dict(state.get("climate_survival"))
    survival = _safe_dict(climate.get("survival"))
    resources = _safe_dict(_player_state(state).get("resources"))
    return {
        "hunger": _clamp(survival.get("hunger", resources.get("hunger", 0))),
        "thirst": _clamp(survival.get("thirst", resources.get("thirst", 0))),
        "fatigue": _clamp(survival.get("fatigue", resources.get("fatigue", 0))),
    }


def _merge_items(items: List[Dict[str, Any]], incoming: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged = [dict(_safe_dict(item)) for item in items]
    index = {_item_key(item): item for item in merged if _item_key(item)}
    for raw in incoming:
        item = dict(_safe_dict(raw))
        key = _item_key(item)
        if not key:
            continue
        qty = _item_qty(item)
        if key in index:
            existing = index[key]
            existing["quantity"] = _item_qty(existing) + qty
        else:
            item["quantity"] = qty
            merged.append(item)
            index[key] = item
    return merged


def ensure_survival_starter_supply(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Seed starter food/water/currency without duplicating existing supply."""

    state = simulation_state if isinstance(simulation_state, dict) else {}
    inventory = _inventory_state(state)
    starter = _safe_dict(SURVIVAL_BALANCE_CONFIG.get("starter_supply"))
    before_items = deepcopy(_safe_list(inventory.get("items")))
    inventory["items"] = _merge_items(_safe_list(inventory.get("items")), _safe_list(starter.get("items")))
    currency = normalize_currency(inventory.get("currency") or starter.get("currency"))
    if currency == {"gold": 0, "silver": 0, "copper": 0}:
        currency = normalize_currency(starter.get("currency"))
    inventory["currency"] = currency
    return {
        "applied": True,
        "source": "n1243_survival_starter_supply",
        "items_before_count": len(before_items),
        "items_after_count": len(_safe_list(inventory.get("items"))),
        "food_available": survival_food_available(state),
        "drink_available": survival_drink_available(state),
    }


def list_survival_shop_supply(provider_id: str = "") -> List[Dict[str, Any]]:
    providers = [provider_id] if provider_id else sorted(SURVIVAL_SHOP_SUPPLIES.keys())
    offers: List[Dict[str, Any]] = []
    for pid in providers:
        offers.extend(deepcopy(_safe_list(SURVIVAL_SHOP_SUPPLIES.get(pid))))
    return offers


def list_survival_service_supply(provider_id: str = "") -> List[Dict[str, Any]]:
    providers = [provider_id] if provider_id else ["npc:Bran"]
    offers: List[Dict[str, Any]] = []
    for pid in providers:
        for kind in (SERVICE_KIND_MEAL, SERVICE_KIND_DRINK, SERVICE_KIND_LODGING):
            offers.extend(get_provider_offers(pid, kind))
    return offers


def survival_food_available(simulation_state: Dict[str, Any]) -> bool:
    return any(_item_qty(_safe_dict(item)) > 0 and _is_food(_safe_dict(item)) for item in _safe_list(_inventory_state(simulation_state).get("items")))


def survival_drink_available(simulation_state: Dict[str, Any]) -> bool:
    return any(_item_qty(_safe_dict(item)) > 0 and _is_drink(_safe_dict(item)) for item in _safe_list(_inventory_state(simulation_state).get("items")))


def build_survival_supply_metrics(transcript_or_states: List[Dict[str, Any]]) -> Dict[str, Any]:
    food_available_turns = 0
    drink_available_turns = 0
    starvation_risk_turns = 0
    dehydration_risk_turns = 0
    for row in _safe_list(transcript_or_states):
        state = _safe_dict(row.get("simulation_state") or row.get("state") or row)
        needs = _needs_from_state(state)
        if survival_food_available(state):
            food_available_turns += 1
        if survival_drink_available(state):
            drink_available_turns += 1
        if needs["hunger"] >= SURVIVAL_BALANCE_CONFIG["severe_threshold"]:
            starvation_risk_turns += 1
        if needs["thirst"] >= SURVIVAL_BALANCE_CONFIG["severe_threshold"]:
            dehydration_risk_turns += 1
    return {
        "format_version": "n1243_survival_supply_metrics_v1",
        "food_available_turns": food_available_turns,
        "drink_available_turns": drink_available_turns,
        "starvation_risk_turns": starvation_risk_turns,
        "dehydration_risk_turns": dehydration_risk_turns,
    }


def _suggestions_from_context(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    suggestions = _safe_list(
        context.get("survival_suggested_actions")
        or _safe_dict(context.get("turn_contract")).get("survival_suggested_actions")
        or _safe_dict(context.get("presentation")).get("survival_suggested_actions")
    )
    if not suggestions:
        suggestions = [item for item in _safe_list(context.get("suggested_actions")) if _safe_dict(item).get("type") == "survival_relief"]
    return [dict(_safe_dict(item)) for item in suggestions]


def build_survival_autoplay_context(
    *,
    simulation_state: Dict[str, Any] | None = None,
    turn_contract: Dict[str, Any] | None = None,
    presentation: Dict[str, Any] | None = None,
    suggested_actions: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    state = _safe_dict(simulation_state)
    contract = _safe_dict(turn_contract)
    presentation = _safe_dict(presentation)
    needs = _needs_from_state(state)
    suggestions = _safe_list(contract.get("survival_suggested_actions") or presentation.get("survival_suggested_actions") or suggested_actions)
    if not suggestions and state:
        suggestions = build_survival_suggested_actions(state)
    high_pressure_stats = [key for key, value in needs.items() if value >= SURVIVAL_BALANCE_CONFIG["pressure_threshold"]]
    severe_stats = [key for key, value in needs.items() if value >= SURVIVAL_BALANCE_CONFIG["severe_threshold"]]
    return {
        "format_version": "n1241_survival_autoplay_context_v1",
        "needs": needs,
        "high_pressure_stats": high_pressure_stats,
        "severe_stats": severe_stats,
        "survival_suggested_actions": suggestions,
        "suggested_actions": suggestions + _safe_list(suggested_actions or contract.get("suggested_actions")),
        "policy": "Prefer deterministic survival relief when high pressure exists; prefer inventory relief before service purchase.",
    }


def choose_survival_aware_action(context: Dict[str, Any]) -> Dict[str, Any]:
    """Choose a deterministic survival relief command from action context."""

    context = _safe_dict(context)
    suggestions = _suggestions_from_context(context)
    needs = _safe_dict(context.get("needs"))
    high_pressure = _safe_list(context.get("high_pressure_stats")) or [key for key, value in needs.items() if _safe_int(value) >= SURVIVAL_BALANCE_CONFIG["pressure_threshold"]]
    if not high_pressure or not suggestions:
        return {"selected": False, "reason": "no_survival_pressure_or_suggestion"}

    by_kind: Dict[str, List[Dict[str, Any]]] = {}
    for suggestion in suggestions:
        by_kind.setdefault(_safe_str(suggestion.get("action_kind")), []).append(suggestion)

    priority = list(SURVIVAL_BALANCE_CONFIG["autoplay_priority"])
    if _safe_int(needs.get("fatigue"), 0) >= SURVIVAL_BALANCE_CONFIG["severe_threshold"] and "buy_lodging" in by_kind:
        priority = ["drink_water", "eat_food", "buy_lodging", "rest", "buy_drink", "buy_meal"]

    for kind in priority:
        if kind in by_kind:
            selected = dict(by_kind[kind][0])
            selected.setdefault("command", selected.get("label") or kind)
            return {
                "selected": True,
                "source": "n1241_survival_aware_autoplay_policy",
                "action_kind": kind,
                "command": selected.get("command"),
                "suggestion": selected,
                "reason": "survival_pressure_relief_priority",
            }
    return {"selected": False, "reason": "no_priority_survival_suggestion"}


def build_survival_autoplay_response_metrics(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    seen = 0
    taken = 0
    ignored = 0
    high_pressure_unanswered = 0
    blocked_relief_loop_count = 0
    last_blocked = ""
    blocked_streak = 0

    for row in _safe_list(transcript):
        row = _safe_dict(row)
        contract = _safe_dict(row.get("turn_contract") or row.get("contract"))
        state = _safe_dict(row.get("simulation_state") or row.get("state"))
        needs = _needs_from_state(state) if state else _safe_dict(row.get("needs"))
        suggestions = _safe_list(row.get("survival_suggested_actions") or contract.get("survival_suggested_actions"))
        action = _safe_dict(row.get("survival_action") or contract.get("survival_action"))
        action_kind = _safe_str(action.get("action_kind") or row.get("selected_action_kind"))
        high_pressure = any(_safe_int(needs.get(key), 0) >= SURVIVAL_BALANCE_CONFIG["pressure_threshold"] for key in ("hunger", "thirst", "fatigue"))
        if suggestions:
            seen += 1
            suggestion_kinds = {_safe_str(item.get("action_kind")) for item in suggestions}
            if action_kind in suggestion_kinds and action.get("applied", row.get("selected_action_taken", True)) is not False:
                taken += 1
            else:
                ignored += 1
        if high_pressure and not action.get("applied"):
            high_pressure_unanswered += 1
        if action.get("blocked") or action.get("blocked_reason"):
            reason = _safe_str(action.get("blocked_reason") or "blocked")
            blocked_streak = blocked_streak + 1 if reason == last_blocked else 1
            last_blocked = reason
            if blocked_streak >= 2:
                blocked_relief_loop_count += 1
        else:
            blocked_streak = 0
            last_blocked = ""

    return {
        "format_version": "n1241_survival_autoplay_response_metrics_v1",
        "survival_suggestion_seen_count": seen,
        "survival_suggestion_taken_count": taken,
        "survival_suggestion_ignored_count": ignored,
        "high_pressure_unanswered_turn_count": high_pressure_unanswered,
        "blocked_relief_loop_count": blocked_relief_loop_count,
        "taken_rate": (taken / seen) if seen else 0.0,
    }


def run_survival_balance_simulation(turns: int = 100, *, use_policy: bool = True) -> Dict[str, Any]:
    needs = {"hunger": 0, "thirst": 0, "fatigue": 0}
    inventory = {"food": 3, "drink": 3}
    rows: List[Dict[str, Any]] = []
    warning_turns = 0
    relief_count = 0
    blocked_relief_count = 0
    for turn in range(1, max(0, turns) + 1):
        for key, delta in SURVIVAL_BALANCE_CONFIG["per_turn_deltas"].items():
            needs[key] = _clamp(needs[key] + delta)
        action_kind = ""
        blocked = False
        if use_policy:
            if needs["thirst"] >= SURVIVAL_BALANCE_CONFIG["pressure_threshold"]:
                if inventory["drink"] > 0:
                    inventory["drink"] -= 1
                    needs["thirst"] = _clamp(needs["thirst"] - SURVIVAL_BALANCE_CONFIG["relief_amounts"]["drink_water"]["thirst"])
                    action_kind = "drink_water"
                    relief_count += 1
                else:
                    blocked = True
                    blocked_relief_count += 1
            elif needs["hunger"] >= SURVIVAL_BALANCE_CONFIG["pressure_threshold"]:
                if inventory["food"] > 0:
                    inventory["food"] -= 1
                    needs["hunger"] = _clamp(needs["hunger"] - SURVIVAL_BALANCE_CONFIG["relief_amounts"]["eat_food"]["hunger"])
                    action_kind = "eat_food"
                    relief_count += 1
                else:
                    blocked = True
                    blocked_relief_count += 1
            elif needs["fatigue"] >= SURVIVAL_BALANCE_CONFIG["pressure_threshold"]:
                needs["fatigue"] = _clamp(needs["fatigue"] - SURVIVAL_BALANCE_CONFIG["relief_amounts"]["rest"]["fatigue"])
                action_kind = "rest"
                relief_count += 1
        warnings = [key for key, value in needs.items() if value >= SURVIVAL_BALANCE_CONFIG["warning_threshold"]]
        if warnings:
            warning_turns += 1
        rows.append({"turn_index": turn, **needs, "action_kind": action_kind, "blocked": blocked, "warnings": warnings, "inventory": dict(inventory)})
    return {
        "format_version": "n1242_survival_balance_simulation_v1",
        "turns": turns,
        "rows": rows,
        "relief_action_count": relief_count,
        "blocked_relief_count": blocked_relief_count,
        "warning_turn_count": warning_turns,
        "warning_turn_rate": (warning_turns / turns) if turns else 0.0,
        "final_needs": dict(needs),
        "max_needs": {
            "hunger": max([row["hunger"] for row in rows] or [0]),
            "thirst": max([row["thirst"] for row in rows] or [0]),
            "fatigue": max([row["fatigue"] for row in rows] or [0]),
        },
    }


def build_survival_response_readiness_gate(summary_or_metrics: Dict[str, Any]) -> Dict[str, Any]:
    data = _safe_dict(summary_or_metrics)
    metrics = _safe_dict(data.get("survival_autoplay_response_metrics") or data)
    pressure_summary = _safe_dict(data.get("survival_pressure_relief_summary"))
    thresholds = _safe_dict(SURVIVAL_BALANCE_CONFIG.get("advisory_thresholds"))
    high_unanswered = _safe_int(metrics.get("high_pressure_unanswered_turn_count"), 0)
    blocked_loop = _safe_int(metrics.get("blocked_relief_loop_count"), 0)
    seen = _safe_int(metrics.get("survival_suggestion_seen_count"), 0)
    taken_rate = float(metrics.get("taken_rate") or 0.0)
    relief_count = _safe_int(metrics.get("survival_suggestion_taken_count"), _safe_int(pressure_summary.get("relief_action_count"), 0))
    pressure_count = _safe_int(pressure_summary.get("pressure_turn_count"), 0)
    ok = True
    reasons: List[str] = []
    if high_unanswered > _safe_int(thresholds.get("max_high_pressure_unanswered_turns"), 5):
        ok = False
        reasons.append("too_many_high_pressure_unanswered_turns")
    if blocked_loop > _safe_int(thresholds.get("max_blocked_relief_loop_count"), 3):
        ok = False
        reasons.append("blocked_relief_loop_count_too_high")
    if seen and taken_rate < float(thresholds.get("min_taken_rate_when_suggestions_seen", 0.20)):
        ok = False
        reasons.append("survival_suggestion_taken_rate_too_low")
    if pressure_count and relief_count <= 0:
        ok = False
        reasons.append("no_relief_actions_despite_survival_pressure")
    return {
        "gate": "survival_response_ok",
        "ok": ok,
        "advisory_only": True,
        "source": "n1244_survival_autoplay_readiness_gate",
        "reasons": reasons,
        "metrics": metrics,
        "thresholds": thresholds,
    }
