"""Bundle BP — deterministic survival autoplay auto-care policy.

The policy reads the same survival action context projected for UI/autoplay and
chooses a bounded survival command without using an LLM.  It prefers inventory
care actions first, then purchase/service fallbacks, while suppressing recently
blocked commands to avoid loops.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

SURVIVAL_AUTOCARE_SOURCE = "runtime_survival_autocare_policy"
SURVIVAL_AUTOCARE_VERSION = "survival_autocare_policy_v1"

_NEEDS: Tuple[str, str, str] = ("thirst", "hunger", "fatigue")
_PRESSURE_RANK = {"low": 0, "moderate": 1, "high": 2, "critical": 3}
_NEED_ACTIONS: Dict[str, Tuple[str, ...]] = {
    "thirst": ("drink water", "drink from waterskin", "buy water", "fill waterskin"),
    "hunger": ("eat rations", "eat food", "buy rations", "buy meal"),
    "fatigue": ("rest", "sleep", "make camp", "buy lodging"),
}
_FALLBACK_ACTIONS: Dict[str, Tuple[str, ...]] = {
    "thirst": ("buy water", "fill waterskin"),
    "hunger": ("buy rations", "buy meal"),
    "fatigue": ("rest", "sleep", "buy lodging"),
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


def _norm_action(value: Any) -> str:
    return " ".join(_safe_str(value).strip().lower().replace("_", " ").replace(":", " ").split())


def _pressure_label(value: Any) -> str:
    label = _safe_str(value).strip().lower()
    return label if label in _PRESSURE_RANK else "low"


def _item_count(simulation_state: Mapping[str, Any], names: Iterable[str]) -> int:
    names = {_norm_action(name) for name in names}
    player_state = _safe_dict(_safe_dict(simulation_state).get("player_state"))
    inventory = _safe_dict(player_state.get("inventory") or player_state.get("inventory_state"))
    total = 0
    for item in _safe_list(inventory.get("items")):
        item = _safe_dict(item)
        haystack = " ".join(
            _norm_action(value)
            for value in (
                item.get("item_id"),
                item.get("definition_id"),
                item.get("name"),
                item.get("kind"),
                " ".join(_safe_str(tag) for tag in _safe_list(item.get("tags"))),
            )
        )
        if any(name in haystack for name in names):
            total += max(1, _safe_int(item.get("quantity"), 1))
    return total


def _has_water(simulation_state: Mapping[str, Any]) -> bool:
    return _item_count(simulation_state, ("water", "waterskin")) > 0


def _has_food(simulation_state: Mapping[str, Any]) -> bool:
    return _item_count(simulation_state, ("ration", "rations", "food", "meal")) > 0


def _currency_amount(simulation_state: Mapping[str, Any]) -> int:
    player_state = _safe_dict(_safe_dict(simulation_state).get("player_state"))
    inventory = _safe_dict(player_state.get("inventory") or player_state.get("inventory_state"))
    currency = _safe_dict(inventory.get("currency") or player_state.get("currency"))
    # Copper-equivalent, intentionally rough and deterministic for prioritizing care.
    return (
        _safe_int(currency.get("gold"), 0) * 100
        + _safe_int(currency.get("silver"), 0) * 10
        + _safe_int(currency.get("copper"), 0)
    )


def _available_actions(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    payload = _safe_dict(payload)
    result = _safe_dict(payload.get("result") or payload)
    contract = _safe_dict(payload.get("turn_contract") or result.get("turn_contract"))
    context = _safe_dict(result.get("survival_action_context") or contract.get("survival_action_context"))
    rows = []
    for source in (
        context.get("suggested_actions"),
        context.get("next_actions"),
        result.get("suggested_actions"),
        result.get("next_actions"),
        contract.get("suggested_actions"),
        contract.get("next_actions"),
    ):
        for item in _safe_list(source):
            item = dict(_safe_dict(item))
            action = _norm_action(item.get("command") or item.get("action") or item.get("label") or item.get("action_id"))
            if not action:
                continue
            item["_normalized_action"] = action.replace("survival ", "", 1)
            rows.append(item)
    return rows


def _recent_blocked_actions(history: Iterable[Mapping[str, Any]], *, window: int = 6) -> Dict[str, int]:
    blocked: Dict[str, int] = {}
    rows = list(history or [])[-window:]
    for row in rows:
        row = _safe_dict(row)
        for candidate in (row, _safe_dict(row.get("result")), _safe_dict(row.get("turn_contract"))):
            survival_result = _safe_dict(candidate.get("survival_result"))
            if survival_result.get("ok") is False or survival_result.get("blocked_reason"):
                action = _norm_action(survival_result.get("action"))
                if action:
                    blocked[action] = blocked.get(action, 0) + 1
        for blocked_action in _safe_list(row.get("blocked_actions")):
            action = _norm_action(_safe_dict(blocked_action).get("action"))
            if action:
                blocked[action] = blocked.get(action, 0) + 1
    return blocked


def _payload_pressure(payload: Mapping[str, Any], simulation_state: Mapping[str, Any]) -> Dict[str, str]:
    payload = _safe_dict(payload)
    result = _safe_dict(payload.get("result") or payload)
    contract = _safe_dict(payload.get("turn_contract") or result.get("turn_contract"))
    context = _safe_dict(result.get("survival_action_context") or contract.get("survival_action_context"))
    pressure = _safe_dict(result.get("survival_pressure") or contract.get("survival_pressure") or context.get("survival_pressure"))
    if pressure:
        return {need: _pressure_label(pressure.get(need)) for need in ("hunger", "thirst", "fatigue")}
    survival = _safe_dict(result.get("survival") or contract.get("survival") or context.get("survival") or _safe_dict(simulation_state).get("survival"))
    out: Dict[str, str] = {}
    for need in ("hunger", "thirst", "fatigue"):
        value = _safe_int(survival.get(need), 0)
        if value >= 75:
            out[need] = "critical"
        elif value >= 50:
            out[need] = "high"
        elif value >= 25:
            out[need] = "moderate"
        else:
            out[need] = "low"
    return out


def _inventory_preferred_action(need: str, simulation_state: Mapping[str, Any]) -> Optional[str]:
    if need == "thirst" and _has_water(simulation_state):
        return "drink water"
    if need == "hunger" and _has_food(simulation_state):
        return "eat rations"
    if need == "fatigue":
        return "rest"
    return None


def choose_survival_autocare_action(
    *,
    payload: Mapping[str, Any],
    simulation_state: Mapping[str, Any],
    recent_history: Optional[Iterable[Mapping[str, Any]]] = None,
    min_pressure: str = "high",
) -> Dict[str, Any]:
    pressure = _payload_pressure(payload, simulation_state)
    available = _available_actions(payload)
    blocked = _recent_blocked_actions(recent_history or [])
    min_rank = _PRESSURE_RANK.get(_pressure_label(min_pressure), 2)

    needs = sorted(
        _NEEDS,
        key=lambda need: (_PRESSURE_RANK.get(pressure.get(need, "low"), 0), 1 if need == "thirst" else 0),
        reverse=True,
    )
    candidates: List[Tuple[str, str, str]] = []
    for need in needs:
        rank = _PRESSURE_RANK.get(pressure.get(need, "low"), 0)
        if rank < min_rank:
            continue
        inventory_action = _inventory_preferred_action(need, simulation_state)
        if inventory_action:
            candidates.append((need, inventory_action, "inventory"))
        for action in _NEED_ACTIONS.get(need, ()):  # context-backed action first when present
            if any(row.get("_normalized_action") == action for row in available):
                candidates.append((need, action, "context"))
        if _currency_amount(simulation_state) > 0:
            for action in _FALLBACK_ACTIONS.get(need, ()):  # deterministic purchase/service fallback
                candidates.append((need, action, "fallback"))

    seen: set[str] = set()
    for need, action, source in candidates:
        if action in seen:
            continue
        seen.add(action)
        normalized_for_block = action.replace(" ", "_")
        if blocked.get(normalized_for_block, 0) >= 2 or blocked.get(action, 0) >= 2:
            continue
        return {
            "ok": True,
            "action": action,
            "need": need,
            "pressure": pressure.get(need, "low"),
            "source": SURVIVAL_AUTOCARE_SOURCE,
            "format_version": SURVIVAL_AUTOCARE_VERSION,
            "selection_source": source,
            "blocked_recently": dict(blocked),
        }

    return {
        "ok": False,
        "action": "",
        "reason": "no_viable_survival_autocare_action",
        "pressure": pressure,
        "source": SURVIVAL_AUTOCARE_SOURCE,
        "format_version": SURVIVAL_AUTOCARE_VERSION,
        "blocked_recently": dict(blocked),
    }


def attach_survival_autocare_policy(
    payload: Mapping[str, Any],
    simulation_state: Mapping[str, Any],
    recent_history: Optional[Iterable[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    out = dict(_safe_dict(payload))
    decision = choose_survival_autocare_action(
        payload=out,
        simulation_state=simulation_state,
        recent_history=recent_history,
    )
    out["survival_autocare_policy"] = decision
    if decision.get("ok") and decision.get("action"):
        next_actions = list(_safe_list(out.get("next_actions")))
        action = _safe_str(decision.get("action"))
        if not any(_norm_action(row.get("action") or row.get("command")) == _norm_action(action) for row in next_actions if isinstance(row, dict)):
            next_actions.insert(0, {
                "action_id": "survival_autocare:" + action.replace(" ", "_"),
                "action": action,
                "action_type": "survival",
                "reason": f"{decision.get('need')} pressure is {decision.get('pressure')}",
                "source": SURVIVAL_AUTOCARE_SOURCE,
            })
        out["next_actions"] = next_actions[:8]
    return out
