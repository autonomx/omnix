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
    return sorted(NEEDS, key=lambda need: (-_safe_int(values.get(need), 0), need))


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


def choose_survival_autoplay_suggestion(session: Dict[str, Any]) -> Dict[str, Any]:
    """Choose one deterministic survival suggestion for the autoplay agent.

    Suggestions come from N123.3, so inventory/service availability is already
    checked before this selector sees a command. This function only chooses a
    priority order: most pressured need first, then the first matching backed
    command for that need.
    """

    session = _safe_dict(session)
    simulation_state = _simulation_state(session)
    runtime_state = _runtime_state(session)
    if not simulation_state:
        return {"promoted": False, "reason": "missing_simulation_state", "source": SOURCE}

    values = _survival_values(simulation_state)
    if max(values.values() or [0]) < 50:
        return {"promoted": False, "reason": "survival_pressure_below_threshold", "needs": values, "source": SOURCE}

    suggestions = [dict(_safe_dict(item)) for item in build_survival_suggested_actions(simulation_state, runtime_state) if isinstance(item, dict)]
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
