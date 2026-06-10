"""CF.2/CE.3 - deterministic survival presentation repair for interactive CLI.

The fast/deferred matrix path keeps runtime turns quick, but provider narration
can be generic or stale for direct survival commands. This repair only rewrites
player-facing presentation from authoritative survival state and resource
changes already present in the turn result.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Tuple

SURVIVAL_REPAIR_SOURCE = "interactive_cli_survival_repair_v1"
SURVIVAL_NEEDS = ("hunger", "thirst", "fatigue")


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


def _walk(value: Any, *, depth: int = 0, max_depth: int = 8) -> Iterable[Dict[str, Any]]:
    if depth > max_depth:
        return
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk(nested, depth=depth + 1, max_depth=max_depth)
    elif isinstance(value, list):
        for item in value[:200]:
            yield from _walk(item, depth=depth + 1, max_depth=max_depth)


def _contains_any(text: str, terms: Tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _is_sell_or_trade_text(player_input: str) -> bool:
    text = _safe_str(player_input).strip().lower()
    if not _contains_any(text, ("sell", "sold", "trade", "barter", "value", "worth", "copper would you give", "give me for")):
        return False
    return _contains_any(text, ("ration", "rations", "provision", "provisions", "item", "gear", "inventory"))


def _is_survival_text(player_input: str) -> bool:
    text = _safe_str(player_input).strip().lower()
    return _contains_any(
        text,
        (
            "hunger",
            "hungry",
            "thirst",
            "thirsty",
            "fatigue",
            "tired",
            "survival",
            "waterskin",
            "drink water",
            "drink from",
            "ration",
            "rations",
            "eat ",
            "consume ",
        ),
    )


def _extract_survival_state(raw_result: Mapping[str, Any]) -> Dict[str, Any]:
    for item in _walk(raw_result):
        survival = _safe_dict(item.get("survival"))
        if all(need in survival for need in SURVIVAL_NEEDS):
            return survival
        climate = _safe_dict(item.get("climate_survival"))
        climate_survival = _safe_dict(climate.get("survival"))
        if all(need in climate_survival for need in SURVIVAL_NEEDS):
            return climate_survival
    return {}


def _survival_action_matches_input(action: Mapping[str, Any], player_input: str) -> bool:
    if _is_sell_or_trade_text(player_input):
        return False
    action_text = _safe_str(_safe_dict(action).get("action") or _safe_dict(action).get("action_kind")).lower()
    input_text = _safe_str(player_input).lower()
    if ("ration" in input_text or "eat" in input_text) and ("ration" in action_text or "eat" in action_text or "food" in action_text):
        return True
    if ("water" in input_text or "waterskin" in input_text or "drink" in input_text) and ("water" in action_text or "waterskin" in action_text or "drink" in action_text):
        return True
    if ("rest" in input_text or "sleep" in input_text or "fatigue" in input_text) and ("rest" in action_text or "sleep" in action_text):
        return True
    return False


def _survival_action_score(action: Mapping[str, Any], player_input: str) -> Tuple[int, int, int, int]:
    action = _safe_dict(action)
    return (
        1 if _survival_action_matches_input(action, player_input) else 0,
        1 if action.get("applied") is True else 0,
        0 if action.get("blocked") or action.get("blocked_reason") else 1,
        1 if _safe_list(action.get("inventory_consumed")) else 0,
    )


def _extract_survival_action(raw_result: Mapping[str, Any], *, player_input: str) -> Dict[str, Any]:
    candidates: List[Dict[str, Any]] = []
    for item in _walk(raw_result):
        action = _safe_dict(item.get("survival_action"))
        if action and (action.get("applied") is not None or action.get("blocked") is not None or action.get("blocked_reason")):
            candidates.append(action)
        nested = _safe_dict(_safe_dict(item.get("effect_result")).get("survival_action"))
        if nested and (nested.get("applied") is not None or nested.get("blocked") is not None or nested.get("blocked_reason")):
            candidates.append(nested)
    if not candidates:
        return {}
    candidates.sort(key=lambda action: _survival_action_score(action, player_input), reverse=True)
    return deepcopy(candidates[0])


def _item_name(item: Mapping[str, Any]) -> str:
    item = _safe_dict(item)
    return _safe_str(item.get("name") or item.get("item_id") or "item").strip() or "item"


def _need_line(survival: Mapping[str, Any]) -> str:
    survival = _safe_dict(survival)
    return ", ".join(f"{need} {_safe_int(survival.get(need), 0)}" for need in SURVIVAL_NEEDS)


def _action_need(action: Mapping[str, Any], player_input: str) -> str:
    action = _safe_dict(action)
    need = _safe_str(action.get("need")).strip().lower()
    if need in SURVIVAL_NEEDS:
        return need
    text = _safe_str(action.get("action") or player_input).lower()
    if "drink" in text or "water" in text or "waterskin" in text:
        return "thirst"
    if "eat" in text or "ration" in text or "food" in text:
        return "hunger"
    if "rest" in text or "sleep" in text:
        return "fatigue"
    return ""


def _format_survival_response(player_input: str, raw_result: Mapping[str, Any]) -> Dict[str, Any]:
    text = _safe_str(player_input).lower()
    action = _extract_survival_action(raw_result, player_input=player_input)
    survival = _safe_dict(action.get("after")) or _extract_survival_state(raw_result)
    before = _safe_dict(action.get("before"))
    consumed = [_safe_dict(item) for item in _safe_list(action.get("inventory_consumed")) if _safe_dict(item)]
    blocked = bool(action.get("blocked") or action.get("blocked_reason"))
    reason = _safe_str(action.get("blocked_reason") or action.get("reason"))
    need = _action_need(action, player_input)

    if action and blocked:
        if need == "thirst":
            line = "You cannot drink from a waterskin because no waterskin is available."
        elif need == "hunger":
            line = "You cannot eat a ration because no ration is available."
        else:
            line = f"The survival action is unavailable: {reason or 'unavailable'}."
        return {
            "narration": line,
            "npc": {"speaker": "", "line": ""},
            "visible_interaction_reason": reason or "survival_action_blocked",
            "survival_action": action,
            "survival": survival,
        }

    if action and action.get("applied") is True:
        item_text = f" You consume {', '.join(_item_name(item) for item in consumed)}." if consumed else ""
        before_value = _safe_int(before.get(need), 0) if need else 0
        after_value = _safe_int(survival.get(need), 0) if need else 0
        if need == "thirst":
            line = f"You drink water from your waterskin; thirst improves from {before_value} to {after_value}.{item_text}"
        elif need == "hunger":
            line = f"You eat a ration; hunger improves from {before_value} to {after_value}.{item_text}"
        elif need == "fatigue":
            line = f"You rest; fatigue improves from {before_value} to {after_value}.{item_text}"
        else:
            line = f"You complete the survival action. Current survival state: {_need_line(survival)}.{item_text}"
        return {
            "narration": line,
            "npc": {"speaker": "", "line": ""},
            "visible_interaction_reason": "survival_action_applied",
            "survival_action": action,
            "survival": survival,
        }

    if _contains_any(text, ("hunger", "hungry", "thirst", "thirsty", "fatigue", "tired", "survival")):
        line = f"Your survival state is {_need_line(survival)}."
        return {
            "narration": line,
            "npc": {"speaker": "", "line": ""},
            "visible_interaction_reason": "survival_state_reported",
            "survival_action": action,
            "survival": survival,
        }

    return {}


def apply_survival_visible_response_repair(turn_summary: Mapping[str, Any], *, player_input: str) -> Dict[str, Any]:
    out = deepcopy(_safe_dict(turn_summary))
    if _safe_dict(out.get("interactive_cli_commerce_followup")).get("applied"):
        return out
    if _safe_dict(out.get("interactive_cli_quest_followup")).get("applied"):
        return out
    if _is_sell_or_trade_text(player_input):
        return out
    if not _is_survival_text(player_input):
        return out

    raw_result = deepcopy(_safe_dict(out.get("raw_result") or out.get("result")))
    response = _format_survival_response(player_input, raw_result)
    if not response:
        return out

    raw_result["narration"] = response["narration"]
    raw_result["npc"] = response["npc"]
    raw_result["visible_interaction_reason"] = response["visible_interaction_reason"]
    raw_result["interactive_cli_survival_repair"] = {
        "applied": True,
        "source": SURVIVAL_REPAIR_SOURCE,
        "survival": response["survival"],
        "survival_action": response["survival_action"],
    }
    contract = deepcopy(_safe_dict(raw_result.get("turn_contract")))
    contract["survival"] = response["survival"]
    if response["survival_action"]:
        contract["survival_action"] = response["survival_action"]
    raw_result["turn_contract"] = contract

    out["raw_result"] = raw_result
    out["raw_narration"] = response["narration"]
    out["raw_npc"] = response["npc"]
    out["narration_preview"] = response["narration"]
    extracted = deepcopy(_safe_dict(out.get("extracted")))
    extracted["narration"] = response["narration"]
    extracted["action"] = response["visible_interaction_reason"]
    extracted["npc_speaker"] = ""
    extracted["npc_line"] = ""
    out["extracted"] = extracted
    out["interactive_cli_survival_repair"] = raw_result["interactive_cli_survival_repair"]
    warnings = list(_safe_list(out.get("scenario_warnings")))
    warning = "interactive_cli_survival_visible_response_repaired"
    if warning not in warnings:
        warnings.append(warning)
    out["scenario_warnings"] = warnings
    return out
