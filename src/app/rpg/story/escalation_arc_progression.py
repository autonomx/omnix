from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Tuple


@dataclass(frozen=True)
class EscalationArcProgressionRule:
    id: str
    arc_id: str
    from_stage: str = "seeded_escalation"
    to_stage: str = ""
    requires_turns_since_started: int = 0
    requires_faction_tier: Tuple[str, str] = ("", "")
    set_flags: Tuple[str, ...] = ()
    world_signals: Tuple[Dict[str, Any], ...] = ()
    pressure_events: Tuple[Dict[str, Any], ...] = ()
    summary: str = ""


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
    rule: EscalationArcProgressionRule,
    *,
    arc: Mapping[str, Any],
    state: Mapping[str, Any],
    turn_index: int,
) -> bool:
    if _safe_str(arc.get("status")) in {"completed", "failed", "abandoned"}:
        return False

    if not bool(arc.get("escalation_arc")) and _safe_str(arc.get("current_stage")) != "seeded_escalation":
        return False

    if rule.from_stage and _safe_str(arc.get("current_stage")) != rule.from_stage:
        return False

    started_turn = int(arc.get("started_turn") or 0)
    if rule.requires_turns_since_started > 0:
        if not started_turn or turn_index - started_turn < rule.requires_turns_since_started:
            return False

    if rule.requires_faction_tier:
        faction_id, required_tier = rule.requires_faction_tier
        if not _tier_requirement_met(_faction_tier(state, faction_id), required_tier):
            return False

    return True


def progress_escalation_arcs(
    *,
    story_arcs: Mapping[str, Any],
    state: Mapping[str, Any],
    turn_index: int,
    rules: Iterable[EscalationArcProgressionRule],
    already_progressed_keys: Iterable[str] = (),
) -> Dict[str, Any]:
    arcs = {
        str(arc_id): dict(_safe_dict(arc))
        for arc_id, arc in _safe_dict(story_arcs).items()
    }

    applied = set(str(key) for key in already_progressed_keys)
    events: List[Dict[str, Any]] = []
    world_signals: List[Dict[str, Any]] = []
    pressure_events: List[Dict[str, Any]] = []
    flags: Dict[str, bool] = {}
    newly_applied_keys: List[str] = []

    for rule in rules:
        arc = _safe_dict(arcs.get(rule.arc_id))
        if not arc:
            continue

        key = f"{rule.arc_id}|{rule.id}|{rule.from_stage}|{rule.to_stage}"
        if key in applied:
            continue

        if not _rule_met(rule, arc=arc, state=state, turn_index=turn_index):
            continue

        previous_stage = _safe_str(arc.get("current_stage"))
        next_stage = rule.to_stage or previous_stage

        arc["current_stage"] = next_stage
        arc["last_progress_turn"] = int(turn_index)
        arc["progress_count"] = int(arc.get("progress_count") or 0) + 1
        arc.setdefault("history", []).append(
            {
                "turn": turn_index,
                "type": "escalation_arc_progressed",
                "rule_id": rule.id,
                "from_stage": previous_stage,
                "to_stage": next_stage,
                "summary": rule.summary,
            }
        )
        arcs[rule.arc_id] = arc

        for flag in rule.set_flags:
            flags[flag] = True
        for signal in rule.world_signals:
            world_signals.append(dict(signal))
        for event in rule.pressure_events:
            pressure_events.append(dict(event))

        events.append(
            {
                "type": "story_arc",
                "subtype": "escalation_arc_progressed",
                "arc_id": rule.arc_id,
                "rule_id": rule.id,
                "from_stage": previous_stage,
                "to_stage": next_stage,
                "summary": rule.summary,
                "meaningful_progress": True,
                "progress_category": "escalation_arc_progression",
            }
        )

        applied.add(key)
        newly_applied_keys.append(key)

    return {
        "ok": True,
        "story_arcs": arcs,
        "events": events,
        "world_signals": world_signals,
        "pressure_events": pressure_events,
        "flags": flags,
        "applied_keys": sorted(applied),
        "newly_applied_keys": newly_applied_keys,
        "progressed_count": len(events),
    }