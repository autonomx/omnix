from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Tuple


@dataclass(frozen=True)
class FactionConsequenceRule:
    id: str
    faction_id: str
    consequence_kind: str
    required_tier: str = ""
    required_arc_stage: Tuple[str, ...] = ()
    required_signal_kind: str = ""
    required_combat_outcome: str = ""
    cooldown_turns: int = 20
    severity: int = 1
    reputation_delta: int = 0
    event: Dict[str, Any] | None = None
    world_signal: Dict[str, Any] | None = None
    set_flags: Tuple[str, ...] = ()


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


def _faction_row(state: Mapping[str, Any], faction_id: str) -> Dict[str, Any]:
    return _safe_dict(_safe_dict(state.get("faction_reputation")).get(faction_id))


def _has_signal_kind(state: Mapping[str, Any], kind: str) -> bool:
    if not kind:
        return True
    for signal in _safe_list(state.get("world_signals")):
        if _safe_str(_safe_dict(signal).get("kind")) == kind:
            return True
    return False


def _has_combat_outcome(state: Mapping[str, Any], outcome: str) -> bool:
    if not outcome:
        return True
    combat = _safe_dict(state.get("combat_lifecycle_summary"))
    by_outcome = _safe_dict(combat.get("by_outcome"))
    return int(by_outcome.get(outcome) or 0) > 0


def _rule_met(
    rule: FactionConsequenceRule,
    *,
    state: Mapping[str, Any],
    turn_index: int,
    last_emitted_turn_by_rule: Mapping[str, Any],
) -> bool:
    faction = _faction_row(state, rule.faction_id)

    if rule.required_tier:
        if not _tier_requirement_met(_safe_str(faction.get("tier") or "neutral"), rule.required_tier):
            return False

    if rule.required_arc_stage:
        arc_id, stage = rule.required_arc_stage
        arc = _safe_dict(_safe_dict(state.get("story_arcs")).get(arc_id))
        if _safe_str(arc.get("current_stage")) != _safe_str(stage):
            return False

    if not _has_signal_kind(state, rule.required_signal_kind):
        return False

    if not _has_combat_outcome(state, rule.required_combat_outcome):
        return False

    last_turn = int(_safe_dict(last_emitted_turn_by_rule).get(rule.id) or 0)
    if last_turn and int(turn_index) - last_turn < int(rule.cooldown_turns or 0):
        return False

    return True


def _apply_reputation_delta(
    faction_reputation: Mapping[str, Any],
    faction_id: str,
    delta: int,
    *,
    turn_index: int,
    reason: str,
) -> Dict[str, Any]:
    factions = dict(_safe_dict(faction_reputation))
    row = dict(_safe_dict(factions.get(faction_id)))
    current = int(row.get("reputation") or 0)
    updated = current + int(delta or 0)

    row["faction_id"] = faction_id
    row["reputation"] = updated
    row.setdefault("tier", "neutral")

    history = _safe_list(row.get("history"))
    history.append(
        {
            "turn": int(turn_index),
            "delta": int(delta or 0),
            "reason": reason,
            "source": "faction_consequence",
        }
    )
    row["history"] = history[-25:]
    factions[faction_id] = row
    return factions


def emit_faction_consequences(
    *,
    state: Mapping[str, Any],
    turn_index: int,
    rules: Iterable[FactionConsequenceRule],
    last_emitted_turn_by_rule: Mapping[str, Any] | None = None,
    max_events_per_turn: int = 2,
) -> Dict[str, Any]:
    faction_reputation = dict(_safe_dict(state.get("faction_reputation")))
    last_emitted = {
        str(key): int(value or 0)
        for key, value in _safe_dict(last_emitted_turn_by_rule).items()
    }

    events: List[Dict[str, Any]] = []
    world_signals: List[Dict[str, Any]] = []
    flags: Dict[str, bool] = {}

    for rule in rules:
        if len(events) >= int(max_events_per_turn):
            break

        if not _rule_met(
            rule,
            state={**_safe_dict(state), "faction_reputation": faction_reputation},
            turn_index=turn_index,
            last_emitted_turn_by_rule=last_emitted,
        ):
            continue

        event = dict(rule.event or {})
        event.setdefault("type", "faction_consequence")
        event.setdefault("subtype", rule.consequence_kind)
        event.setdefault("rule_id", rule.id)
        event.setdefault("faction_id", rule.faction_id)
        event.setdefault("turn", int(turn_index))
        event.setdefault("severity", int(rule.severity))
        event.setdefault("reputation_delta", int(rule.reputation_delta or 0))
        event.setdefault("meaningful_progress", True)
        event.setdefault("progress_category", "faction_consequence")
        events.append(event)

        if int(rule.reputation_delta or 0) != 0:
            faction_reputation = _apply_reputation_delta(
                faction_reputation,
                rule.faction_id,
                int(rule.reputation_delta or 0),
                turn_index=turn_index,
                reason=rule.consequence_kind,
            )

        if rule.world_signal:
            signal = dict(rule.world_signal)
            signal.setdefault("kind", "faction_consequence")
            signal.setdefault("faction_id", rule.faction_id)
            signal.setdefault("turn", int(turn_index))
            signal.setdefault("created_turn", int(turn_index))
            signal.setdefault("ttl_turns", 60)
            signal.setdefault("intensity", int(rule.severity))
            world_signals.append(signal)

        for flag in rule.set_flags:
            flags[str(flag)] = True

        last_emitted[rule.id] = int(turn_index)

    return {
        "ok": True,
        "faction_reputation": faction_reputation,
        "events": events,
        "world_signals": world_signals,
        "flags": flags,
        "last_emitted_turn_by_rule": last_emitted,
        "event_count": len(events),
    }