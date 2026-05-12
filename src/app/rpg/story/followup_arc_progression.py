from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Tuple


@dataclass(frozen=True)
class FollowupArcProgressionRule:
    id: str
    arc_id: str
    from_stage: str = "seeded_followup"
    to_stage: str = ""
    requires_turns_since_started: int = 0
    requires_faction_tier: Tuple[str, str] = ()
    requires_flags: Tuple[str, ...] = ()
    blocked_by_flags: Tuple[str, ...] = ()
    set_flags: Tuple[str, ...] = ()
    world_signals: Tuple[Dict[str, Any], ...] = ()
    followup_hooks: Tuple[Dict[str, Any], ...] = ()
    summary: str = ""


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return str(value or "")


def _state_flags(state: Mapping[str, Any]) -> set[str]:
    flags: set[str] = set()
    raw_flags = state.get("flags")
    if isinstance(raw_flags, dict):
        flags.update(str(k) for k, v in raw_flags.items() if v)
    elif isinstance(raw_flags, list):
        flags.update(str(v) for v in raw_flags)
    return flags


def _faction_tier(state: Mapping[str, Any], faction_id: str) -> str:
    factions = _safe_dict(state.get("faction_reputation"))
    faction = _safe_dict(factions.get(faction_id))
    return _safe_str(faction.get("tier") or "neutral")


def _rule_met(
    rule: FollowupArcProgressionRule,
    *,
    arc: Mapping[str, Any],
    state: Mapping[str, Any],
    turn_index: int,
) -> bool:
    if rule.from_stage and _safe_str(arc.get("current_stage")) != rule.from_stage:
        return False

    started_turn = int(arc.get("started_turn") or 0)
    if rule.requires_turns_since_started > 0:
        if not started_turn or turn_index - started_turn < rule.requires_turns_since_started:
            return False

    flags = _state_flags(state)
    if any(flag not in flags for flag in rule.requires_flags):
        return False
    if any(flag in flags for flag in rule.blocked_by_flags):
        return False

    if rule.requires_faction_tier:
        faction_id, required_tier = rule.requires_faction_tier
        if _faction_tier(state, faction_id) != required_tier:
            return False

    return True


def progress_followup_arcs(
    *,
    story_arcs: Mapping[str, Any],
    state: Mapping[str, Any],
    turn_index: int,
    rules: Iterable[FollowupArcProgressionRule],
    already_progressed_keys: Iterable[str] = (),
) -> Dict[str, Any]:
    arcs = {
        str(arc_id): dict(_safe_dict(arc))
        for arc_id, arc in _safe_dict(story_arcs).items()
    }

    applied = set(str(key) for key in already_progressed_keys)
    events: List[Dict[str, Any]] = []
    world_signals: List[Dict[str, Any]] = []
    followup_hooks: List[Dict[str, Any]] = []
    flags: Dict[str, bool] = {}
    newly_applied_keys: List[str] = []

    for rule in rules:
        arc = _safe_dict(arcs.get(rule.arc_id))
        if not arc:
            continue
        if _safe_str(arc.get("status")) in {"completed", "failed", "abandoned"}:
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
                "type": "followup_arc_progressed",
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
        for hook in rule.followup_hooks:
            followup_hooks.append(dict(hook))

        event = {
            "type": "story_arc",
            "subtype": "followup_arc_progressed",
            "arc_id": rule.arc_id,
            "rule_id": rule.id,
            "from_stage": previous_stage,
            "to_stage": next_stage,
            "summary": rule.summary,
            "meaningful_progress": True,
            "progress_category": "followup_arc_progression",
        }
        events.append(event)

        applied.add(key)
        newly_applied_keys.append(key)

    return {
        "ok": True,
        "story_arcs": arcs,
        "events": events,
        "world_signals": world_signals,
        "followup_hooks": followup_hooks,
        "flags": flags,
        "applied_keys": sorted(applied),
        "newly_applied_keys": newly_applied_keys,
        "progressed_count": len(events),
    }