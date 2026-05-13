from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Tuple


@dataclass(frozen=True)
class NPCAgencyRule:
    id: str
    npc_id: str
    required_location_id: str = ""
    required_activity_contains: str = ""
    required_arc_stage: Tuple[str, str] = ()
    required_faction_tier: Tuple[str, str] = ()
    cooldown_turns: int = 10
    event: Dict[str, Any] | None = None
    world_signal: Dict[str, Any] | None = None
    memory_event: Dict[str, Any] | None = None
    set_flags: Tuple[str, ...] = ()


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return str(value or "")


_TIER_RANK = {
    "hostile": -2,
    "suspicious": -1,
    "neutral": 0,
    "friendly": 1,
    "trusted": 2,
}


def _tier_requirement_met(actual: str, required: str) -> bool:
    actual_rank = _TIER_RANK.get(_safe_str(actual), 0)
    required_rank = _TIER_RANK.get(_safe_str(required), 0)

    if required_rank < 0:
        return actual_rank <= required_rank
    if required_rank > 0:
        return actual_rank >= required_rank
    return actual_rank == required_rank


def _faction_tier(state: Mapping[str, Any], faction_id: str) -> str:
    faction = _safe_dict(_safe_dict(state.get("faction_reputation")).get(faction_id))
    return _safe_str(faction.get("tier") or "neutral")


def _rule_met(
    rule: NPCAgencyRule,
    *,
    state: Mapping[str, Any],
    turn_index: int,
    last_emitted_turn_by_rule: Mapping[str, Any],
) -> bool:
    presence = _safe_dict(_safe_dict(state.get("npc_presence")).get(rule.npc_id))

    if rule.required_location_id:
        if _safe_str(presence.get("location_id")) != rule.required_location_id:
            return False

    if rule.required_activity_contains:
        if rule.required_activity_contains.lower() not in _safe_str(presence.get("activity")).lower():
            return False

    if rule.required_arc_stage:
        arc_id, stage = rule.required_arc_stage
        arc = _safe_dict(_safe_dict(state.get("story_arcs")).get(arc_id))
        if _safe_str(arc.get("current_stage")) != stage:
            return False

    if rule.required_faction_tier:
        faction_id, required_tier = rule.required_faction_tier
        if not _tier_requirement_met(_faction_tier(state, faction_id), required_tier):
            return False

    last_turn = int(_safe_dict(last_emitted_turn_by_rule).get(rule.id) or 0)
    if last_turn and int(turn_index) - last_turn < int(rule.cooldown_turns):
        return False

    return True


def emit_npc_agency_events(
    *,
    state: Mapping[str, Any],
    turn_index: int,
    rules: Iterable[NPCAgencyRule],
    last_emitted_turn_by_rule: Mapping[str, Any] | None = None,
    max_events_per_turn: int = 2,
) -> Dict[str, Any]:
    last_emitted = {
        str(k): int(v or 0)
        for k, v in _safe_dict(last_emitted_turn_by_rule).items()
    }

    events: List[Dict[str, Any]] = []
    world_signals: List[Dict[str, Any]] = []
    memory_events: List[Dict[str, Any]] = []
    flags: Dict[str, bool] = {}

    for rule in rules:
        if len(events) >= int(max_events_per_turn):
            break

        if not _rule_met(
            rule,
            state=state,
            turn_index=turn_index,
            last_emitted_turn_by_rule=last_emitted,
        ):
            continue

        presence = _safe_dict(_safe_dict(state.get("npc_presence")).get(rule.npc_id))

        event = dict(rule.event or {})
        event.setdefault("type", "npc_agency")
        event.setdefault("subtype", "agency_tick")
        event.setdefault("npc_id", rule.npc_id)
        event.setdefault("location_id", presence.get("location_id"))
        event.setdefault("activity", presence.get("activity"))
        event.setdefault("turn", int(turn_index))
        event.setdefault("meaningful_progress", False)
        event.setdefault("progress_category", "npc_agency")
        events.append(event)

        if rule.world_signal:
            signal = dict(rule.world_signal)
            signal.setdefault("npc_id", rule.npc_id)
            signal.setdefault("turn", int(turn_index))
            signal.setdefault("created_turn", int(turn_index))
            world_signals.append(signal)

        if rule.memory_event:
            memory = dict(rule.memory_event)
            memory.setdefault("npc_id", rule.npc_id)
            memory.setdefault("turn", int(turn_index))
            memory.setdefault("created_turn", int(turn_index))
            memory_events.append(memory)

        for flag in rule.set_flags:
            flags[str(flag)] = True

        last_emitted[rule.id] = int(turn_index)

    return {
        "ok": True,
        "events": events,
        "world_signals": world_signals,
        "memory_events": memory_events,
        "flags": flags,
        "last_emitted_turn_by_rule": last_emitted,
        "event_count": len(events),
    }