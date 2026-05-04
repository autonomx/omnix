from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.campaign_journal.journal import record_campaign_journal_entry
from app.rpg.story_arcs.milestones import get_story_arc_milestone
from app.rpg.story_events.effects import apply_story_event_effect
from app.rpg.story_events.state import (
    has_story_event_been_applied,
    mark_story_event_applied,
)
from app.rpg.story_events.validation import validate_story_event


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def apply_story_event(
    simulation_state: Dict[str, Any],
    event: Dict[str, Any],
    *,
    turn_index: int = 0,
) -> Dict[str, Any]:
    event = _safe_dict(event)
    event_id = str(event.get("event_id") or "")
    if not event_id:
        return {
            "ok": False,
            "reason": "missing_event_id",
            "event_id": "",
        }

    if has_story_event_been_applied(simulation_state, event_id):
        return {
            "ok": True,
            "reason": "already_applied",
            "event_id": event_id,
            "effect_results": [],
            "applied_once": True,
        }

    validation = validate_story_event(simulation_state, event)
    if not validation.get("ok"):
        return {
            "ok": False,
            "reason": "validation_failed",
            "event_id": event_id,
            "validation": validation,
            "effect_results": [],
        }

    effect_results: List[Dict[str, Any]] = []
    for effect in event.get("effects") or []:
        if not isinstance(effect, dict):
            continue
        result = apply_story_event_effect(
            simulation_state,
            effect,
            source_event=event,
            turn_index=turn_index,
        )
        effect_results.append(result)
        if not result.get("ok"):
            return {
                "ok": False,
                "reason": "effect_apply_failed",
                "event_id": event_id,
                "failed_effect": effect,
                "effect_results": effect_results,
            }

    applied = mark_story_event_applied(
        simulation_state,
        event,
        effect_results=effect_results,
        turn_index=turn_index,
    )
    record_campaign_journal_entry(
        simulation_state,
        kind="story_event",
        title=str(event.get("title") or event.get("kind") or "Story Event"),
        summary=str(event.get("summary") or event_id),
        turn_index=turn_index,
        visibility="player",
        arc_ids=[str(event.get("arc_id") or "")] if event.get("arc_id") else [],
        event_ids=[event_id],
        npc_ids=[str(npc_id) for npc_id in event.get("participants") or [] if str(npc_id)],
        source_id=event_id,
        metadata={"source": "apply_story_event"},
    )
    for effect_result in effect_results or []:
        if not isinstance(effect_result, dict):
            continue
        result_payload = effect_result.get("result") if isinstance(effect_result.get("result"), dict) else effect_result
        if result_payload.get("reason") not in {"completed", "already_completed"}:
            continue
        milestone = result_payload.get("milestone")
        if not isinstance(milestone, dict):
            milestone = get_story_arc_milestone(
                simulation_state,
                str(result_payload.get("milestone_id") or ""),
            )
        if not isinstance(milestone, dict):
            continue
        summary = milestone.get("journal_on_complete") or milestone.get("summary") or milestone.get("title")
        if not summary:
            continue
        record_campaign_journal_entry(
            simulation_state,
            kind="objective",
            title=str(milestone.get("title") or "Objective Updated"),
            summary=str(summary),
            turn_index=turn_index,
            visibility="player",
            fact_status="confirmed",
            arc_ids=[str(milestone.get("arc_id") or "")] if milestone.get("arc_id") else [],
            event_ids=[event_id],
            quest_ids=[str(milestone.get("quest_id") or "")] if milestone.get("quest_id") else [],
            tags=["objective", "milestone"],
            source_id=str(milestone.get("milestone_id") or ""),
            metadata={"source": "milestone_complete"},
        )
    return {
        "ok": True,
        "reason": "applied",
        "event_id": event_id,
        "arc_id": event.get("arc_id") or "",
        "kind": event.get("kind") or "event",
        "summary": event.get("summary") or "",
        "effect_results": effect_results,
        "applied": applied,
        "applied_once": True,
    }