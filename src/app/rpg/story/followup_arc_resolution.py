from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Tuple


@dataclass(frozen=True)
class FollowupArcResolutionRule:
    id: str
    arc_id: str
    from_stage: str = ""
    outcome: str = "resolved"
    status: str = "completed"
    requires_stage: str = ""
    requires_turns_since_progress: int = 0
    requires_flags: Tuple[str, ...] = ()
    requires_faction_tier: Tuple[str, str] = ()
    blocked_by_flags: Tuple[str, ...] = ()
    reward_xp: int = 0
    world_signals: Tuple[Dict[str, Any], ...] = ()
    faction_deltas: Tuple[Dict[str, Any], ...] = ()
    escalation_hooks: Tuple[Dict[str, Any], ...] = ()
    set_flags: Tuple[str, ...] = ()
    summary: str = ""


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return str(value or "")


def _state_flags(state: Mapping[str, Any]) -> set[str]:
    flags: set[str] = set()
    raw = state.get("flags")
    if isinstance(raw, dict):
        flags.update(str(k) for k, v in raw.items() if v)
    elif isinstance(raw, list):
        flags.update(str(v) for v in raw)
    return flags


def _faction_tier(state: Mapping[str, Any], faction_id: str) -> str:
    faction = _safe_dict(_safe_dict(state.get("faction_reputation")).get(faction_id))
    return _safe_str(faction.get("tier") or "neutral")


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


def _rule_met(
    rule: FollowupArcResolutionRule,
    *,
    arc: Mapping[str, Any],
    state: Mapping[str, Any],
    turn_index: int,
) -> bool:
    stage = _safe_str(arc.get("current_stage"))

    if rule.from_stage and stage != rule.from_stage:
        return False
    if rule.requires_stage and stage != rule.requires_stage:
        return False

    if rule.requires_turns_since_progress > 0:
        last_progress_turn = int(arc.get("last_progress_turn") or arc.get("started_turn") or 0)
        if not last_progress_turn or turn_index - last_progress_turn < rule.requires_turns_since_progress:
            return False

    flags = _state_flags(state)
    if any(flag not in flags for flag in rule.requires_flags):
        return False
    if any(flag in flags for flag in rule.blocked_by_flags):
        return False

    if rule.requires_faction_tier:
        faction_id, tier = rule.requires_faction_tier
        if not _tier_requirement_met(_faction_tier(state, faction_id), tier):
            return False

    return True


def resolve_followup_arcs(
    *,
    story_arcs: Mapping[str, Any],
    state: Mapping[str, Any],
    turn_index: int,
    rules: Iterable[FollowupArcResolutionRule],
    already_resolved_keys: Iterable[str] = (),
) -> Dict[str, Any]:
    arcs = {
        str(arc_id): dict(_safe_dict(arc))
        for arc_id, arc in _safe_dict(story_arcs).items()
    }

    applied = set(str(key) for key in already_resolved_keys)

    events: List[Dict[str, Any]] = []
    world_signals: List[Dict[str, Any]] = []
    faction_deltas: List[Dict[str, Any]] = []
    escalation_hooks: List[Dict[str, Any]] = []
    flags: Dict[str, bool] = {}
    newly_applied_keys: List[str] = []
    xp_delta = 0

    for rule in rules:
        arc = _safe_dict(arcs.get(rule.arc_id))
        if not arc:
            continue

        if _safe_str(arc.get("status")) in {"completed", "failed", "abandoned"}:
            continue

        key = f"{rule.arc_id}|{rule.id}|{rule.outcome}|{rule.status}"
        if key in applied:
            continue

        if not _rule_met(rule, arc=arc, state=state, turn_index=turn_index):
            continue

        previous_stage = _safe_str(arc.get("current_stage"))
        arc["status"] = rule.status
        arc["resolution_outcome"] = rule.outcome
        arc["completed_turn" if rule.status == "completed" else "failed_turn"] = int(turn_index)
        arc["last_progress_turn"] = int(turn_index)
        arc["progress_count"] = int(arc.get("progress_count") or 0) + 1
        arc.setdefault("history", []).append(
            {
                "turn": turn_index,
                "type": "followup_arc_resolved",
                "rule_id": rule.id,
                "from_stage": previous_stage,
                "status": rule.status,
                "outcome": rule.outcome,
                "summary": rule.summary,
            }
        )

        arcs[rule.arc_id] = arc

        for flag in rule.set_flags:
            flags[flag] = True
        for signal in rule.world_signals:
            world_signals.append(dict(signal))
        for delta in rule.faction_deltas:
            faction_deltas.append(dict(delta))
        for hook in rule.escalation_hooks:
            escalation_hooks.append(dict(hook))

        if rule.reward_xp:
            xp_delta += int(rule.reward_xp)

        events.append(
            {
                "type": "story_arc",
                "subtype": "followup_arc_resolved",
                "arc_id": rule.arc_id,
                "rule_id": rule.id,
                "from_stage": previous_stage,
                "status": rule.status,
                "outcome": rule.outcome,
                "summary": rule.summary,
                "meaningful_progress": True,
                "progress_category": "followup_arc_resolution",
            }
        )

        applied.add(key)
        newly_applied_keys.append(key)

    return {
        "ok": True,
        "story_arcs": arcs,
        "events": events,
        "world_signals": world_signals,
        "faction_deltas": faction_deltas,
        "escalation_hooks": escalation_hooks,
        "flags": flags,
        "xp_delta": xp_delta,
        "applied_keys": sorted(applied),
        "newly_applied_keys": newly_applied_keys,
        "resolved_count": len(events),
    }