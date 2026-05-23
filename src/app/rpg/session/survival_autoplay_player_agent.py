from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.rpg.session.survival_actions import build_survival_suggested_actions

NEEDS = ("hunger", "thirst", "fatigue")
NEED_ACTIONS = {
    "thirst": ("drink_water", "buy_drink"),
    "hunger": ("eat_food", "buy_meal"),
    "fatigue": ("rest", "buy_lodging"),
}
SOURCE = "n1272_survival_autoplay_player_agent"
CRITICAL_THIRST_SOURCE = "n1279_thirst_critical_relief_priority"
CRITICAL_THIRST_THRESHOLD = 90
CAPPED_THIRST_THRESHOLD = 100


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


def _simulation_state(session: Dict[str, Any]) -> Dict[str, Any]:
    session = _safe_dict(session)
    simulation_state = _safe_dict(session.get("simulation_state"))
    if simulation_state:
        return simulation_state
    state = _safe_dict(session.get("state"))
    return _safe_dict(state.get("simulation_state")) or state


def _runtime_state(session: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(_safe_dict(session).get("runtime_state"))


def _survival_values(simulation_state: Dict[str, Any]) -> Dict[str, int]:
    simulation_state = _safe_dict(simulation_state)
    climate = _safe_dict(simulation_state.get("climate_survival"))
    survival = _safe_dict(climate.get("survival"))
    player_state = _safe_dict(simulation_state.get("player_state"))
    resources = _safe_dict(player_state.get("resources"))
    needs = _safe_dict(simulation_state.get("needs"))
    return {
        need: max(0, min(100, _safe_int(survival.get(need, resources.get(need, needs.get(need, 0))), 0)))
        for need in NEEDS
    }


def _already_survival_command(player_input: str) -> bool:
    text = _safe_str(player_input).strip().lower()
    if not text:
        return False
    return any(term in text for term in ("drink", "waterskin", "water", "eat", "ration", "food", "meal", "rest", "sleep", "rent room", "buy drink", "buy meal"))


def _need_priority(values: Dict[str, int]) -> List[str]:
    # Keep the normal selector simple, but make ties deterministic in favour of
    # thirst because its deterministic tick rises faster than hunger/fatigue.
    tie_break = {"thirst": 0, "hunger": 1, "fatigue": 2}
    return sorted(NEEDS, key=lambda need: (-_safe_int(values.get(need), 0), tie_break.get(need, 99), need))


def _suggestion_action_kind(suggestion: Dict[str, Any]) -> str:
    return _safe_str(
        suggestion.get("action_kind")
        or suggestion.get("kind")
        or suggestion.get("type")
        or suggestion.get("need")
    )


def _suggestion_command(suggestion: Dict[str, Any]) -> str:
    command = _safe_str(suggestion.get("command")).strip()
    if command:
        return command
    label = _safe_str(suggestion.get("label") or suggestion.get("action")).strip()
    if label:
        return label if label.lower().startswith("i ") else f"I {label[0].lower()}{label[1:] if len(label) > 1 else ''}"
    need = _safe_str(suggestion.get("need"))
    if need == "thirst":
        return "I drink water"
    if need == "hunger":
        return "I eat food"
    if need == "fatigue":
        return "I rest"
    return ""


def _inventory_items(simulation_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    player_state = _safe_dict(_safe_dict(simulation_state).get("player_state"))
    inventory = _safe_dict(player_state.get("inventory_state"))
    return [dict(_safe_dict(item)) for item in _safe_list(inventory.get("items")) if isinstance(item, dict)]


def _item_quantity(item: Dict[str, Any]) -> int:
    return max(0, _safe_int(_safe_dict(item).get("quantity", _safe_dict(item).get("qty", 1)), 1))


def _item_name(item: Dict[str, Any]) -> str:
    item = _safe_dict(item)
    return _safe_str(item.get("name") or item.get("label") or item.get("item_id") or item.get("id") or "item")


def _item_identity(item: Dict[str, Any]) -> str:
    item = _safe_dict(item)
    return _safe_str(item.get("item_id") or item.get("id") or item.get("key") or item.get("name")).lower()


def _item_tags(item: Dict[str, Any]) -> List[str]:
    item = _safe_dict(item)
    tags: List[str] = []
    for key in ("tags", "item_tags", "categories"):
        tags.extend(_safe_str(value).lower() for value in _safe_list(item.get(key)))
    kind = _safe_str(item.get("kind") or item.get("type") or item.get("category")).lower()
    if kind:
        tags.append(kind)
    return tags


def _is_drink_item(item: Dict[str, Any]) -> bool:
    item = _safe_dict(item)
    if _item_quantity(item) <= 0:
        return False
    haystack = " ".join([_item_identity(item), _item_name(item).lower()] + _item_tags(item))
    return any(term in haystack for term in ("drink", "water", "waterskin", "ale", "wine", "beer", "canteen"))


def _drink_inventory_suggestion(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    for item in _inventory_items(simulation_state):
        if not _is_drink_item(item):
            continue
        name = _item_name(item)
        return {
            "type": "survival_relief",
            "source": CRITICAL_THIRST_SOURCE,
            "action_kind": "drink_water",
            "label": f"Drink {name}",
            "command": f"I drink {name}",
            "reason": "critical_thirst_inventory_drink_available",
            "item_id": _safe_str(item.get("item_id") or item.get("id") or item.get("name")),
            "quantity": _item_quantity(item),
        }
    return {}


def _critical_thirst_active(values: Dict[str, int], runtime_state: Dict[str, Any]) -> bool:
    thirst = _safe_int(values.get("thirst"), 0)
    if thirst >= CRITICAL_THIRST_THRESHOLD:
        return True
    # Cadence guard: if prior turn was capped and current is still high, keep
    # drink priority active even if a recent drink nudged thirst just below the
    # hard threshold for one tick.
    history = _safe_list(runtime_state.get("survival_autoplay_promotion_history"))
    for row in reversed(history[-4:]):
        row = _safe_dict(row)
        needs = _safe_dict(row.get("needs"))
        if _safe_int(needs.get("thirst"), 0) >= CAPPED_THIRST_THRESHOLD and thirst >= 80:
            return True
    return False


def _last_relief_kind(runtime_state: Dict[str, Any]) -> str:
    history = _safe_list(runtime_state.get("survival_autoplay_promotion_history"))
    for row in reversed(history):
        row = _safe_dict(row)
        action_kind = _safe_str(row.get("action_kind"))
        if action_kind:
            return action_kind
    last = _safe_dict(runtime_state.get("last_survival_autoplay_promotion"))
    return _safe_str(last.get("action_kind"))


def _critical_thirst_promotion(
    *,
    values: Dict[str, int],
    runtime_state: Dict[str, Any],
    suggestions: List[Dict[str, Any]],
    simulation_state: Dict[str, Any],
) -> Dict[str, Any]:
    if not _critical_thirst_active(values, runtime_state):
        return {}
    drink_suggestions = [dict(_safe_dict(item)) for item in suggestions if _suggestion_action_kind(_safe_dict(item)) in {"drink_water", "buy_drink"}]
    suggestion = drink_suggestions[0] if drink_suggestions else _drink_inventory_suggestion(simulation_state)
    if not suggestion:
        return {
            "promoted": False,
            "reason": "critical_thirst_no_backed_drink_suggestion",
            "needs": values,
            "suggestion_count": len(suggestions),
            "critical_thirst": True,
            "critical_thirst_source": CRITICAL_THIRST_SOURCE,
            "source": SOURCE,
        }
    command = _suggestion_command(suggestion)
    if not command:
        return {}
    last_kind = _last_relief_kind(runtime_state)
    repeated = last_kind == "drink_water"
    return {
        "promoted": True,
        "command": command,
        "need": "thirst",
        "need_value": values.get("thirst", 0),
        "action_kind": _suggestion_action_kind(suggestion) or "drink_water",
        "suggestion": suggestion,
        "suggestion_count": len(suggestions),
        "needs": values,
        "reason": "critical_thirst_backed_drink_priority" if not repeated else "critical_thirst_cadence_repeat_drink",
        "critical_thirst": True,
        "critical_thirst_source": CRITICAL_THIRST_SOURCE,
        "cadence_guard_active": True,
        "previous_relief_action_kind": last_kind,
        "source": SOURCE,
    }


def choose_survival_autoplay_suggestion(session: Dict[str, Any]) -> Dict[str, Any]:
    """Choose one deterministic survival suggestion for the autoplay agent.

    Suggestions come from N123.3, so inventory/service availability is already
    checked before this selector sees a command. N127.9 adds one explicit policy
    exception: critical thirst outranks rest/eat/normal highest-pressure scoring
    whenever a drink suggestion is backed by inventory/service availability.
    """

    session = _safe_dict(session)
    simulation_state = _simulation_state(session)
    runtime_state = _runtime_state(session)
    if not simulation_state:
        return {"promoted": False, "reason": "missing_simulation_state", "source": SOURCE}

    values = _survival_values(simulation_state)
    if max(values.values() or [0]) < 50 and not _critical_thirst_active(values, runtime_state):
        return {"promoted": False, "reason": "survival_pressure_below_threshold", "needs": values, "source": SOURCE}

    suggestions = [dict(_safe_dict(item)) for item in build_survival_suggested_actions(simulation_state, runtime_state) if isinstance(item, dict)]
    critical = _critical_thirst_promotion(values=values, runtime_state=runtime_state, suggestions=suggestions, simulation_state=simulation_state)
    if critical:
        return critical
    if not suggestions:
        return {"promoted": False, "reason": "no_backed_survival_suggestions", "needs": values, "source": SOURCE}

    for need in _need_priority(values):
        if values.get(need, 0) < 50:
            continue
        allowed = set(NEED_ACTIONS.get(need, ()))
        for suggestion in suggestions:
            action_kind = _suggestion_action_kind(suggestion)
            if action_kind not in allowed:
                continue
            command = _suggestion_command(suggestion)
            if not command:
                continue
            return {
                "promoted": True,
                "command": command,
                "need": need,
                "need_value": values.get(need, 0),
                "action_kind": action_kind,
                "suggestion": suggestion,
                "suggestion_count": len(suggestions),
                "needs": values,
                "reason": "highest_pressure_backed_survival_suggestion",
                "source": SOURCE,
            }

    return {"promoted": False, "reason": "no_matching_need_suggestion", "needs": values, "suggestion_count": len(suggestions), "source": SOURCE}


def promote_survival_suggestion_for_autoplay(session: Dict[str, Any], player_input: str) -> Tuple[str, Dict[str, Any]]:
    promotion = choose_survival_autoplay_suggestion(session)
    if not promotion.get("promoted"):
        return player_input, promotion
    command = _safe_str(promotion.get("command")).strip()
    if not command:
        promotion = dict(promotion)
        promotion["promoted"] = False
        promotion["reason"] = "empty_promoted_command"
        return player_input, promotion
    promotion = dict(promotion)
    promotion["original_player_input"] = _safe_str(player_input)
    promotion["original_was_survival_command"] = _already_survival_command(player_input)
    return command, promotion
