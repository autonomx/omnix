from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Tuple


@dataclass(frozen=True)
class NPCReactionRule:
    id: str
    npc_id: str
    reaction_kind: str
    required_location_id: str = ""
    required_faction_tier: Tuple[str, ...] = ()
    required_consequence_kind: str = ""
    required_flag: str = ""
    cooldown_turns: int = 12
    event: Dict[str, Any] | None = None
    memory_event: Dict[str, Any] | None = None
    world_signal: Dict[str, Any] | None = None


_TIER_RANK = {
    "hostile": -2,
    "suspicious": -1,
    "neutral": 0,
    "friendly": 1,
    "trusted": 2,
}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return str(value or "")


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


def _has_consequence_kind(state: Mapping[str, Any], kind: str) -> bool:
    if not kind:
        return True
    for event in _safe_list(state.get("faction_consequence_events")):
        if _safe_str(_safe_dict(event).get("subtype")) == _safe_str(kind):
            return True
    return False


def _rule_met(
    rule: NPCReactionRule,
    *,
    state: Mapping[str, Any],
    turn_index: int,
    last_emitted_turn_by_rule: Mapping[str, Any],
) -> bool:
    presence = _safe_dict(_safe_dict(state.get("npc_presence")).get(rule.npc_id))

    if rule.required_location_id:
        if _safe_str(presence.get("location_id")) != _safe_str(rule.required_location_id):
            return False

    if rule.required_faction_tier:
        faction_id, tier = rule.required_faction_tier
        if not _tier_requirement_met(_faction_tier(state, faction_id), tier):
            return False

    if rule.required_consequence_kind:
        if not _has_consequence_kind(state, rule.required_consequence_kind):
            return False

    if rule.required_flag:
        if not bool(_safe_dict(state.get("flags")).get(rule.required_flag)):
            return False

    last_turn = int(_safe_dict(last_emitted_turn_by_rule).get(rule.id) or 0)
    if last_turn and int(turn_index) - last_turn < int(rule.cooldown_turns or 0):
        return False

    return True


def emit_npc_reactions(
    *,
    state: Mapping[str, Any],
    turn_index: int,
    rules: Iterable[NPCReactionRule],
    last_emitted_turn_by_rule: Mapping[str, Any] | None = None,
    max_events_per_turn: int = 2,
) -> Dict[str, Any]:
    last_emitted = {
        str(key): int(value or 0)
        for key, value in _safe_dict(last_emitted_turn_by_rule).items()
    }

    events: List[Dict[str, Any]] = []
    memory_events: List[Dict[str, Any]] = []
    world_signals: List[Dict[str, Any]] = []

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
        event.setdefault("type", "npc_reaction")
        event.setdefault("subtype", rule.reaction_kind)
        event.setdefault("rule_id", rule.id)
        event.setdefault("npc_id", rule.npc_id)
        event.setdefault("location_id", presence.get("location_id"))
        event.setdefault("turn", int(turn_index))
        event.setdefault("meaningful_progress", False)
        event.setdefault("progress_category", "npc_reaction")
        events.append(event)

        if rule.memory_event:
            memory = dict(rule.memory_event)
            memory.setdefault("kind", "npc_memory")
            memory.setdefault("type", "npc_reaction")
            memory.setdefault("npc_id", rule.npc_id)
            memory.setdefault("turn", int(turn_index))
            memory.setdefault("created_turn", int(turn_index))
            memory_events.append(memory)

        if rule.world_signal:
            signal = dict(rule.world_signal)
            signal.setdefault("kind", "npc_reaction")
            signal.setdefault("npc_id", rule.npc_id)
            signal.setdefault("turn", int(turn_index))
            signal.setdefault("created_turn", int(turn_index))
            signal.setdefault("ttl_turns", 40)
            world_signals.append(signal)

        last_emitted[rule.id] = int(turn_index)

    return {
        "ok": True,
        "events": events,
        "memory_events": memory_events,
        "world_signals": world_signals,
        "last_emitted_turn_by_rule": last_emitted,
        "event_count": len(events),
    }