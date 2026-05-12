from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Tuple


@dataclass(frozen=True)
class FactionPressureRule:
    id: str
    faction_id: str
    min_reputation: int = -10
    max_reputation: int = 10
    required_tier: str = ""
    cooldown_turns: int = 10
    pressure_event: Dict[str, Any] | None = None
    world_signal: Dict[str, Any] | None = None
    set_flags: Tuple[str, ...] = ()


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return str(value or "")


def emit_faction_pressure_events(
    *,
    faction_state: Mapping[str, Any],
    turn_index: int,
    rules: Iterable[FactionPressureRule],
    last_emitted_turn_by_rule: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    last_emitted = {
        str(k): int(v or 0)
        for k, v in _safe_dict(last_emitted_turn_by_rule).items()
    }

    events: List[Dict[str, Any]] = []
    world_signals: List[Dict[str, Any]] = []
    flags: Dict[str, bool] = {}

    for rule in rules:
        faction = _safe_dict(_safe_dict(faction_state).get(rule.faction_id))
        if not faction:
            continue

        reputation = int(faction.get("reputation") or 0)
        tier = _safe_str(faction.get("tier") or "neutral")

        if reputation < rule.min_reputation or reputation > rule.max_reputation:
            continue
        if rule.required_tier and tier != rule.required_tier:
            continue

        last_turn = int(last_emitted.get(rule.id) or 0)
        if last_turn and turn_index - last_turn < rule.cooldown_turns:
            continue

        event = dict(rule.pressure_event or {})
        if not event:
            event = {
                "type": "faction_pressure",
                "faction_id": rule.faction_id,
                "summary": f"{rule.faction_id} applies pressure.",
            }

        event.setdefault("type", "faction_pressure")
        event.setdefault("faction_id", rule.faction_id)
        event.setdefault("turn", turn_index)
        event.setdefault("meaningful_progress", True)
        event.setdefault("progress_category", "faction_pressure")
        events.append(event)

        if rule.world_signal:
            signal = dict(rule.world_signal)
            signal.setdefault("faction_id", rule.faction_id)
            signal.setdefault("kind", "faction_pressure")
            world_signals.append(signal)

        for flag in rule.set_flags:
            flags[flag] = True

        last_emitted[rule.id] = turn_index

    return {
        "ok": True,
        "events": events,
        "world_signals": world_signals,
        "flags": flags,
        "last_emitted_turn_by_rule": last_emitted,
        "event_count": len(events),
    }