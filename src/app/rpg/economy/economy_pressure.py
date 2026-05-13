from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Tuple


@dataclass(frozen=True)
class EconomyPressureRule:
    id: str
    kind: str
    every_turns: int
    cost_currency: Tuple[str, int] = ("gold", 0)
    required_flag: str = ""
    blocked_flag: str = ""
    world_signal: Dict[str, Any] | None = None
    event: Dict[str, Any] | None = None
    warning_threshold_currency: Tuple[str, int] = ("gold", 0)
    cooldown_turns: int = 0


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return str(value or "")


def _currency_amount(currency: Mapping[str, Any], key: str) -> int:
    try:
        return int(_safe_dict(currency).get(key) or 0)
    except Exception:
        return 0


def _set_currency_amount(currency: Dict[str, Any], key: str, amount: int) -> None:
    currency[str(key)] = max(0, int(amount))


def apply_currency_delta(
    *,
    currency: Mapping[str, Any],
    delta: Mapping[str, Any],
) -> Dict[str, Any]:
    result = dict(_safe_dict(currency))
    for key, raw_amount in _safe_dict(delta).items():
        try:
            amount = int(raw_amount or 0)
        except Exception:
            amount = 0
        _set_currency_amount(result, str(key), _currency_amount(result, str(key)) + amount)
    return result


def _rule_due(
    *,
    rule: EconomyPressureRule,
    turn_index: int,
    flags: Mapping[str, Any],
    last_emitted_turn_by_rule: Mapping[str, Any],
) -> bool:
    if rule.required_flag and not bool(_safe_dict(flags).get(rule.required_flag)):
        return False

    if rule.blocked_flag and bool(_safe_dict(flags).get(rule.blocked_flag)):
        return False

    if int(rule.every_turns) > 0 and int(turn_index) % int(rule.every_turns) != 0:
        return False

    last_turn = int(_safe_dict(last_emitted_turn_by_rule).get(rule.id) or 0)
    if last_turn and int(rule.cooldown_turns) > 0:
        if int(turn_index) - last_turn < int(rule.cooldown_turns):
            return False

    return True


def apply_economy_pressure(
    *,
    economy_state: Mapping[str, Any],
    turn_index: int,
    rules: Iterable[EconomyPressureRule],
    flags: Mapping[str, Any] | None = None,
    last_emitted_turn_by_rule: Mapping[str, Any] | None = None,
    max_events_per_turn: int = 3,
) -> Dict[str, Any]:
    state = dict(_safe_dict(economy_state))
    currency = dict(_safe_dict(state.get("currency")))
    last_emitted = {
        str(k): int(v or 0)
        for k, v in _safe_dict(last_emitted_turn_by_rule).items()
    }

    events: List[Dict[str, Any]] = []
    world_signals: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    applied_rules: List[str] = []
    currency_deltas: List[Dict[str, Any]] = []

    for rule in rules:
        if len(events) >= int(max_events_per_turn):
            break

        if not _rule_due(
            rule=rule,
            turn_index=turn_index,
            flags=_safe_dict(flags),
            last_emitted_turn_by_rule=last_emitted,
        ):
            continue

        currency_key, cost_amount = rule.cost_currency
        cost_amount = int(cost_amount or 0)
        current_amount = _currency_amount(currency, currency_key)

        event = dict(rule.event or {})
        event.setdefault("type", "economy_pressure")
        event.setdefault("subtype", rule.kind)
        event.setdefault("rule_id", rule.id)
        event.setdefault("turn", int(turn_index))
        event.setdefault("currency_key", currency_key)
        event.setdefault("cost_amount", cost_amount)
        event.setdefault("meaningful_progress", False)
        event.setdefault("progress_category", "economy_pressure")

        if cost_amount > 0:
            if current_amount >= cost_amount:
                _set_currency_amount(currency, currency_key, current_amount - cost_amount)
                event["paid"] = True
                event["currency_before"] = current_amount
                event["currency_after"] = _currency_amount(currency, currency_key)
                currency_deltas.append(
                    {
                        "currency": currency_key,
                        "delta": -cost_amount,
                        "reason": rule.kind,
                        "turn": int(turn_index),
                    }
                )
            else:
                event["paid"] = False
                event["shortfall"] = cost_amount - current_amount
                warnings.append(
                    {
                        "type": "economy_warning",
                        "subtype": "insufficient_currency",
                        "rule_id": rule.id,
                        "currency": currency_key,
                        "needed": cost_amount,
                        "available": current_amount,
                        "turn": int(turn_index),
                    }
                )

        warn_key, warn_threshold = rule.warning_threshold_currency
        if warn_threshold and _currency_amount(currency, warn_key) <= int(warn_threshold):
            warnings.append(
                {
                    "type": "economy_warning",
                    "subtype": "low_currency",
                    "rule_id": rule.id,
                    "currency": warn_key,
                    "threshold": int(warn_threshold),
                    "available": _currency_amount(currency, warn_key),
                    "turn": int(turn_index),
                }
            )

        if rule.world_signal:
            signal = dict(rule.world_signal)
            signal.setdefault("kind", "economy_pressure")
            signal.setdefault("turn", int(turn_index))
            signal.setdefault("created_turn", int(turn_index))
            signal.setdefault("ttl_turns", 40)
            world_signals.append(signal)

        events.append(event)
        applied_rules.append(rule.id)
        last_emitted[rule.id] = int(turn_index)

    state["currency"] = currency
    state["last_pressure_turn"] = int(turn_index) if events else state.get("last_pressure_turn")

    return {
        "ok": True,
        "economy_state": state,
        "currency": currency,
        "events": events,
        "world_signals": world_signals,
        "warnings": warnings,
        "currency_deltas": currency_deltas,
        "applied_rules": applied_rules,
        "last_emitted_turn_by_rule": last_emitted,
        "event_count": len(events),
        "warning_count": len(warnings),
    }