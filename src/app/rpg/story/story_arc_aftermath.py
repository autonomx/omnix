from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Tuple


@dataclass(frozen=True)
class ArcAftermathRule:
    id: str
    arc_id: str
    outcome: str = ""
    on_status: str = "completed"
    world_signals: Tuple[Dict[str, Any], ...] = ()
    npc_memory_events: Tuple[Dict[str, Any], ...] = ()
    faction_deltas: Tuple[Dict[str, Any], ...] = ()
    followup_hooks: Tuple[Dict[str, Any], ...] = ()
    set_flags: Tuple[str, ...] = ()
    summary: str = ""


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return str(value or "")


def _arc_event_key(event: Mapping[str, Any]) -> str:
    return "|".join(
        [
            _safe_str(event.get("arc_id")),
            _safe_str(event.get("subtype")),
            _safe_str(event.get("outcome")),
        ]
    )


def apply_story_arc_aftermath(
    *,
    arc_events: Iterable[Mapping[str, Any]],
    already_applied_keys: Iterable[str] = (),
    rules: Iterable[ArcAftermathRule],
) -> Dict[str, Any]:
    applied = set(str(key) for key in already_applied_keys)
    events = [_safe_dict(event) for event in arc_events]

    world_signals: List[Dict[str, Any]] = []
    npc_memory_events: List[Dict[str, Any]] = []
    faction_deltas: List[Dict[str, Any]] = []
    followup_hooks: List[Dict[str, Any]] = []
    flags: Dict[str, bool] = {}
    aftermath_events: List[Dict[str, Any]] = []
    newly_applied_keys: List[str] = []

    for event in events:
        event_key = _arc_event_key(event)
        if not event_key or event_key in applied:
            continue

        arc_id = _safe_str(event.get("arc_id"))
        subtype = _safe_str(event.get("subtype"))
        status = "completed" if subtype == "arc_completed" else "failed"
        outcome = _safe_str(event.get("outcome"))

        for rule in rules:
            if rule.arc_id != arc_id:
                continue
            if rule.on_status != status:
                continue
            if rule.outcome and rule.outcome != outcome:
                continue

            for signal in rule.world_signals:
                world_signals.append(dict(signal))
            for memory in rule.npc_memory_events:
                npc_memory_events.append(dict(memory))
            for delta in rule.faction_deltas:
                faction_deltas.append(dict(delta))
            for hook in rule.followup_hooks:
                followup_hooks.append(dict(hook))
            for flag in rule.set_flags:
                flags[flag] = True

            aftermath_events.append(
                {
                    "type": "story_arc_aftermath",
                    "rule_id": rule.id,
                    "arc_id": arc_id,
                    "status": status,
                    "outcome": outcome,
                    "summary": rule.summary,
                    "meaningful_progress": True,
                    "progress_category": "story_arc_aftermath",
                }
            )

        applied.add(event_key)
        newly_applied_keys.append(event_key)

    return {
        "ok": True,
        "applied_keys": sorted(applied),
        "newly_applied_keys": newly_applied_keys,
        "aftermath_events": aftermath_events,
        "world_signals": world_signals,
        "npc_memory_events": npc_memory_events,
        "faction_deltas": faction_deltas,
        "followup_hooks": followup_hooks,
        "flags": flags,
    }