from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return str(value or "")


def pressure_event_key(event: Mapping[str, Any]) -> str:
    return "|".join(
        [
            _safe_str(event.get("type") or "faction_pressure"),
            _safe_str(event.get("subtype")),
            _safe_str(event.get("faction_id")),
            _safe_str(event.get("summary")),
        ]
    )


def filter_pressure_events_for_pacing(
    *,
    pressure_events: Iterable[Mapping[str, Any]],
    world_signals: Iterable[Mapping[str, Any]],
    turn_index: int,
    emitted_key_turns: Mapping[str, Any],
    min_gap_turns: int = 10,
    max_events_per_turn: int = 1,
) -> Dict[str, Any]:
    emitted = {
        str(key): int(value or 0)
        for key, value in _safe_dict(emitted_key_turns).items()
    }

    accepted_events: List[Dict[str, Any]] = []
    rejected_events: List[Dict[str, Any]] = []
    accepted_signals: List[Dict[str, Any]] = []
    rejected_signals: List[Dict[str, Any]] = []

    for raw_event in pressure_events:
        event = _safe_dict(raw_event)
        key = pressure_event_key(event)
        last_turn = int(emitted.get(key) or 0)

        if len(accepted_events) >= max_events_per_turn:
            rejected_events.append({**event, "pacing_reject_reason": "max_events_per_turn"})
            continue

        if last_turn and turn_index - last_turn < min_gap_turns:
            rejected_events.append({**event, "pacing_reject_reason": "min_gap_turns"})
            continue

        accepted_events.append(event)
        emitted[key] = int(turn_index)

    accepted_factions = {
        _safe_str(event.get("faction_id"))
        for event in accepted_events
        if _safe_str(event.get("faction_id"))
    }

    for raw_signal in world_signals:
        signal = _safe_dict(raw_signal)
        faction_id = _safe_str(signal.get("faction_id"))

        if faction_id and faction_id not in accepted_factions:
            rejected_signals.append({**signal, "pacing_reject_reason": "event_rejected"})
            continue

        if len(accepted_signals) >= max_events_per_turn:
            rejected_signals.append({**signal, "pacing_reject_reason": "max_signals_per_turn"})
            continue

        accepted_signals.append(signal)

    return {
        "ok": True,
        "accepted_events": accepted_events,
        "rejected_events": rejected_events,
        "accepted_world_signals": accepted_signals,
        "rejected_world_signals": rejected_signals,
        "emitted_key_turns": emitted,
        "accepted_count": len(accepted_events),
        "rejected_count": len(rejected_events),
    }