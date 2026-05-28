from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from app.rpg.interactions.item_model import (
    normalize_item_instance,
    recalculate_inventory_derived_fields,
    remove_quantity_from_items_list,
)
from app.rpg.interactions.merchant_runtime import apply_merchant_interaction
from app.rpg.survival import apply_survival_effect, ensure_survival_state

_SURVIVAL_SOURCE = "runtime_action_resolver"
_RUNTIME_SOURCE = "deterministic_survival_action_runtime"

_WATER_TERMS = {"water", "waterskin water", "fresh water", "clean water"}
_WATERSKIN_TERMS = {"waterskin", "water skin", "filled waterskin"}
_RATION_TERMS = {"ration", "rations", "trail ration", "trail rations", "iron ration", "iron rations"}
_FOOD_TERMS = {"food", "meal", "bread", "cheese", "apple", "stew", "provisions"}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", _safe_str(value).strip().lower())


def _tokenize(value: str) -> set[str]:
    normalized = _normalize_text(value).replace("_", " ").replace(":", " ")
    return {part for part in re.split(r"[^a-z0-9]+", normalized) if part}


def _player_inventory(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    player_state = _safe_dict(simulation_state.get("player_state"))
    inventory = _safe_dict(player_state.get("inventory"))
    if not isinstance(inventory.get("items"), list):
        inventory["items"] = []
    if not isinstance(inventory.get("equipment"), dict):
        inventory["equipment"] = {}
    player_state["inventory"] = inventory
    simulation_state["player_state"] = player_state
    return inventory


def _item_search_text(item: Mapping[str, Any]) -> str:
    item = normalize_item_instance(_safe_dict(item))
    parts: List[str] = [
        _safe_str(item.get("item_id")),
        _safe_str(item.get("definition_id")),
        _safe_str(item.get("name")),
        _safe_str(item.get("kind")),
    ]
    parts.extend(_safe_str(alias) for alias in _safe_list(item.get("aliases")))
    parts.extend(_safe_str(tag) for tag in _safe_list(item.get("tags")))
    return _normalize_text(" ".join(parts)).replace("_", " ").replace(":", " ")


def _item_matches_terms(item: Mapping[str, Any], terms: Iterable[str]) -> bool:
    search = _item_search_text(item)
    tokens = _tokenize(search)
    for term in terms:
        term = _normalize_text(term).replace("_", " ")
        if not term:
            continue
        if term in search:
            return True
        term_tokens = _tokenize(term)
        if term_tokens and term_tokens.issubset(tokens):
            return True
    return False


def _find_inventory_item(items: List[Any], terms: Iterable[str]) -> Dict[str, Any]:
    for item in items:
        normalized = normalize_item_instance(_safe_dict(item))
        if _item_matches_terms(normalized, terms):
            return normalized
    return {}


def _remove_one_inventory_item(simulation_state: Dict[str, Any], terms: Iterable[str]) -> Tuple[bool, Dict[str, Any], Dict[str, Any]]:
    inventory = _player_inventory(simulation_state)
    items = [normalize_item_instance(_safe_dict(item)) for item in _safe_list(inventory.get("items"))]
    item = _find_inventory_item(items, terms)
    if not item:
        return False, {}, {
            "removed_all": False,
            "quantity_removed": 0,
            "quantity_missing": 1,
            "source": "deterministic_item_model",
        }

    remove_result = remove_quantity_from_items_list(
        items,
        item_id=_safe_str(item.get("item_id")),
        quantity=1,
    )
    if not remove_result.get("removed_all"):
        return False, item, remove_result

    inventory["items"] = _safe_list(remove_result.get("items"))
    inventory = recalculate_inventory_derived_fields(inventory)
    simulation_state["player_state"]["inventory"] = inventory
    return True, item, remove_result


def _find_charged_waterskin(items: List[Any]) -> Tuple[int, Dict[str, Any], int, str]:
    for index, raw_item in enumerate(items):
        item = normalize_item_instance(_safe_dict(raw_item))
        if not _item_matches_terms(item, _WATERSKIN_TERMS):
            continue
        metadata = _safe_dict(item.get("metadata"))
        state = _safe_dict(item.get("state"))
        if "water_charges" in metadata:
            charges = _safe_int(metadata.get("water_charges"), 0)
            return index, item, charges, "metadata"
        if "water_charges" in state:
            charges = _safe_int(state.get("water_charges"), 0)
            return index, item, charges, "state"
    return -1, {}, 0, ""


def _consume_waterskin_charge(simulation_state: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], Dict[str, Any]]:
    inventory = _player_inventory(simulation_state)
    items = [normalize_item_instance(_safe_dict(item)) for item in _safe_list(inventory.get("items"))]
    index, item, charges, charge_container = _find_charged_waterskin(items)
    if index < 0 or not item:
        return False, {}, {"reason": "no_waterskin_available"}
    if charges <= 0:
        return False, item, {"reason": "waterskin_empty", "charges_before": charges}

    updated = deepcopy(item)
    if charge_container == "metadata":
        metadata = _safe_dict(updated.get("metadata"))
        metadata["water_charges"] = charges - 1
        updated["metadata"] = metadata
    else:
        state = _safe_dict(updated.get("state"))
        state["water_charges"] = charges - 1
        updated["state"] = state

    items[index] = updated
    inventory["items"] = items
    inventory = recalculate_inventory_derived_fields(inventory)
    simulation_state["player_state"]["inventory"] = inventory
    return True, item, {
        "charges_before": charges,
        "charges_after": charges - 1,
        "quantity_removed": 0,
        "source": _RUNTIME_SOURCE,
    }


def detect_survival_action(player_input: str, semantic_action_v2: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Detect concrete survival actions without calling an LLM."""
    raw = _safe_str(player_input)
    text = _normalize_text(raw)
    action = _safe_dict(semantic_action_v2)
    kind = _safe_str(action.get("kind"))
    target = _normalize_text(action.get("target_ref") or action.get("item_ref"))

    if not text:
        return {"detected": False, "reason": "empty_player_input", "source": _RUNTIME_SOURCE}

    has_drink = bool(re.search(r"\b(drink|sip|quaff)\b", text)) or kind in {"consume", "use_item"} and bool(re.search(r"\b(water|waterskin|water skin)\b", target))
    has_eat = bool(re.search(r"\b(eat|consume)\b", text)) or kind in {"consume", "use_item"} and bool(re.search(r"\b(ration|rations|food|meal|bread|provisions)\b", target))
    has_buy = bool(re.search(r"\b(buy|purchase)\b", text)) or kind == "buy"

    if has_buy and re.search(r"\b(water|waterskin|water skin)\b", text):
        return {"detected": True, "action": "buy_water", "target_terms": ["water"], "source": _RUNTIME_SOURCE}
    if has_buy and re.search(r"\b(ration|rations|food|provisions)\b", text):
        return {"detected": True, "action": "buy_rations", "target_terms": ["rations"], "source": _RUNTIME_SOURCE}

    if has_drink and re.search(r"\b(waterskin|water skin)\b", text + " " + target):
        return {"detected": True, "action": "drink_from_waterskin", "target_terms": list(_WATERSKIN_TERMS), "source": _RUNTIME_SOURCE}
    if has_drink and re.search(r"\bwater\b", text + " " + target):
        return {"detected": True, "action": "drink_water", "target_terms": list(_WATER_TERMS), "source": _RUNTIME_SOURCE}

    if has_eat and re.search(r"\b(ration|rations)\b", text + " " + target):
        return {"detected": True, "action": "eat_rations", "target_terms": list(_RATION_TERMS), "source": _RUNTIME_SOURCE}
    if has_eat and re.search(r"\b(food|meal|bread|cheese|apple|stew|provisions)\b", text + " " + target):
        return {"detected": True, "action": "eat_food", "target_terms": list(_FOOD_TERMS), "source": _RUNTIME_SOURCE}

    if re.search(r"\b(make camp|set camp|camp for the night|pitch camp)\b", text):
        return {"detected": True, "action": "make_camp", "target_terms": [], "source": _RUNTIME_SOURCE}
    if re.search(r"\b(sleep|go to sleep|sleep for the night)\b", text):
        return {"detected": True, "action": "sleep", "target_terms": [], "source": _RUNTIME_SOURCE}
    if re.search(r"\b(rest|take a rest|rest awhile|rest for)\b", text):
        return {"detected": True, "action": "rest", "target_terms": [], "source": _RUNTIME_SOURCE}

    return {"detected": False, "reason": "no_survival_action_detected", "source": _RUNTIME_SOURCE}


def _blocked_result(action: Dict[str, Any], reason: str, *, tick: int, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = {
        "resolved": False,
        "changed_state": False,
        "ok": False,
        "action_category": "survival",
        "action": _safe_str(action.get("action")),
        "reason": reason,
        "blocked_reason": reason,
        "tick": int(tick or 0),
        "source": _RUNTIME_SOURCE,
    }
    payload.update(_safe_dict(extra or {}))
    return payload


def _merchant_buy_action_for_survival(action: str, semantic_action_v2: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    semantic = _safe_dict(semantic_action_v2)
    target_ref = "water" if action == "buy_water" else "rations"
    return {
        "resolved": True,
        "kind": "buy",
        "actor_id": _safe_str(semantic.get("actor_id") or "player"),
        "target_ref": target_ref,
        "item_ref": target_ref,
        "secondary_target_ref": _safe_str(semantic.get("secondary_target_ref")),
        "merchant_id": _safe_str(semantic.get("merchant_id") or "npc:Elara"),
        "quantity": max(1, _safe_int(semantic.get("quantity"), 1)),
        "confidence": "high",
        "raw_input": _safe_str(semantic.get("raw_input")),
        "source": _RUNTIME_SOURCE,
    }


def _resolve_survival_purchase(
    simulation_state: Dict[str, Any],
    *,
    action: str,
    semantic_action_v2: Optional[Mapping[str, Any]],
    detected: Dict[str, Any],
    tick: int,
) -> Dict[str, Any]:
    merchant_action = _merchant_buy_action_for_survival(action, semantic_action_v2)
    merchant_result = apply_merchant_interaction(
        simulation_state,
        semantic_action_v2=merchant_action,
        tick=tick,
    )
    survival_state = ensure_survival_state(simulation_state)
    if not merchant_result.get("resolved"):
        return _blocked_result(
            {"action": action},
            _safe_str(merchant_result.get("reason")) or "survival_purchase_failed",
            tick=tick,
            extra={
                "detected": detected,
                "survival": deepcopy(survival_state),
                "merchant_result": deepcopy(merchant_result),
                "forbidden_narration": [
                    "Do not say supplies were bought unless merchant_result.resolved is true.",
                    "Do not add water, rations, or food unless a merchant/service transaction succeeds.",
                ],
            },
        )

    quantity = max(1, _safe_int(merchant_result.get("quantity"), 1))
    inventory_delta = {"water": quantity} if action == "buy_water" else {"rations": quantity}
    survival_event = {
        "kind": action,
        "tick": int(tick or 0),
        "effects": {},
        "inventory_delta": deepcopy(inventory_delta),
        "merchant_result": deepcopy(merchant_result),
        "source": _SURVIVAL_SOURCE,
    }
    survival_state.setdefault("events", [])
    survival_state["events"] = (survival_state.get("events") or [])[-31:] + [survival_event]
    simulation_state["survival"] = survival_state
    return {
        "resolved": True,
        "changed_state": True,
        "ok": True,
        "action_category": "survival",
        "action": action,
        "reason": action,
        "effects": {},
        "inventory_delta": deepcopy(inventory_delta),
        "merchant_result": deepcopy(merchant_result),
        "survival_event": deepcopy(survival_event),
        "survival": deepcopy(survival_state),
        "detected": detected,
        "turn_contract_fragment": {
            "action_category": "survival",
            "action": action,
            "ok": True,
            "effects": {},
            "inventory_delta": deepcopy(inventory_delta),
            "survival_event": deepcopy(survival_event),
        },
        "tick": int(tick or 0),
        "source": _RUNTIME_SOURCE,
    }


def resolve_survival_action(
    simulation_state: Dict[str, Any],
    *,
    player_input: str,
    semantic_action_v2: Optional[Mapping[str, Any]] = None,
    tick: int = 0,
) -> Dict[str, Any]:
    detected = detect_survival_action(player_input, semantic_action_v2)
    if not detected.get("detected"):
        return {
            "resolved": False,
            "changed_state": False,
            "reason": _safe_str(detected.get("reason")) or "no_survival_action_detected",
            "detected": detected,
            "source": _RUNTIME_SOURCE,
        }

    survival_state = ensure_survival_state(simulation_state)
    action = _safe_str(detected.get("action"))
    inventory_delta: Dict[str, int] = {}
    item_result: Dict[str, Any] = {}

    if action in {"buy_water", "buy_rations"}:
        return _resolve_survival_purchase(
            simulation_state,
            action=action,
            semantic_action_v2=semantic_action_v2,
            detected=detected,
            tick=tick,
        )

    if action == "drink_water":
        removed, item, remove_result = _remove_one_inventory_item(simulation_state, _WATER_TERMS)
        if not removed:
            waterskin_removed, waterskin_item, waterskin_result = _consume_waterskin_charge(simulation_state)
            if waterskin_removed:
                action = "drink_from_waterskin"
                item = waterskin_item
                inventory_delta = {"waterskin_water_charges": -1}
            else:
                return _blocked_result(
                    {"action": "drink_water"},
                    "no_water_available",
                    tick=tick,
                    extra={
                        "detected": detected,
                        "survival": deepcopy(survival_state),
                        "inventory_result": deepcopy(remove_result),
                        "waterskin_result": deepcopy(waterskin_result),
                    },
                )
        else:
            item_result = item
            inventory_delta = {"water": -1}

    elif action == "drink_from_waterskin":
        removed, item, remove_result = _consume_waterskin_charge(simulation_state)
        if not removed:
            return _blocked_result(
                {"action": action},
                _safe_str(remove_result.get("reason")) or "no_waterskin_available",
                tick=tick,
                extra={
                    "detected": detected,
                    "survival": deepcopy(survival_state),
                    "waterskin_result": deepcopy(remove_result),
                },
            )
        item_result = item
        inventory_delta = {"waterskin_water_charges": -1}

    elif action == "eat_rations":
        removed, item, remove_result = _remove_one_inventory_item(simulation_state, _RATION_TERMS)
        if not removed:
            return _blocked_result(
                {"action": action},
                "no_rations_available",
                tick=tick,
                extra={
                    "detected": detected,
                    "survival": deepcopy(survival_state),
                    "inventory_result": deepcopy(remove_result),
                },
            )
        item_result = item
        inventory_delta = {"rations": -1}

    elif action == "eat_food":
        removed, item, remove_result = _remove_one_inventory_item(simulation_state, _FOOD_TERMS)
        if not removed:
            return _blocked_result(
                {"action": action},
                "no_food_available",
                tick=tick,
                extra={
                    "detected": detected,
                    "survival": deepcopy(survival_state),
                    "inventory_result": deepcopy(remove_result),
                },
            )
        item_result = item
        inventory_delta = {"food": -1}

    elif action not in {"rest", "sleep", "make_camp"}:
        return _blocked_result(
            {"action": action},
            "unsupported_survival_action",
            tick=tick,
            extra={"detected": detected, "survival": deepcopy(survival_state)},
        )

    effect_result = apply_survival_effect(
        simulation_state,
        kind=action,
        tick=tick,
        source=_SURVIVAL_SOURCE,
    )
    if not effect_result.get("ok"):
        return _blocked_result(
            {"action": action},
            _safe_str(effect_result.get("reason")) or "survival_effect_failed",
            tick=tick,
            extra={"detected": detected, "effect_result": deepcopy(effect_result)},
        )

    survival_event = deepcopy(_safe_dict(effect_result.get("survival_event")))
    survival_event["inventory_delta"] = deepcopy(inventory_delta)

    return {
        "resolved": True,
        "changed_state": True,
        "ok": True,
        "action_category": "survival",
        "action": action,
        "reason": action,
        "effects": deepcopy(_safe_dict(effect_result.get("effects"))),
        "inventory_delta": deepcopy(inventory_delta),
        "inventory_item": deepcopy(item_result),
        "survival_event": survival_event,
        "survival": deepcopy(_safe_dict(effect_result.get("survival"))),
        "detected": detected,
        "turn_contract_fragment": {
            "action_category": "survival",
            "action": action,
            "ok": True,
            "effects": deepcopy(_safe_dict(effect_result.get("effects"))),
            "inventory_delta": deepcopy(inventory_delta),
            "survival_event": survival_event,
        },
        "tick": int(tick or 0),
        "source": _RUNTIME_SOURCE,
    }
