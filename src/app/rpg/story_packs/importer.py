from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

from app.rpg.lore.state import get_lore_entry, upsert_lore_entry
from app.rpg.quests.transitions import apply_quest_transition
from app.rpg.story_arcs.milestones import add_story_arc_milestone
from app.rpg.story_arcs.state import get_story_arc, start_story_arc
from app.rpg.story_packs.definition_registries import (
    register_escalation_rule_definition,
    register_story_event_definition,
)
from app.rpg.story_packs.registry import (
    get_imported_story_pack,
    mark_story_pack_imported,
)
from app.rpg.story_proposals.validation import validate_story_proposal


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _stable_pack_id(proposal: Dict[str, Any]) -> str:
    proposal_id = str(proposal.get("proposal_id") or "").strip()
    if proposal_id:
        return f"storypack:{proposal_id}"
    title = str(proposal.get("title") or "").strip()
    payload = json.dumps(proposal, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    if title:
        slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in title).strip("_")[:40]
        return f"storypack:{slug}:{digest}"
    return f"storypack:{digest}"


def _import_lore_entries(
    simulation_state: Dict[str, Any],
    lore_entries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    results = []
    lore_ids = []
    for entry in lore_entries:
        lore_id = str(entry.get("lore_id") or "")
        if not lore_id:
            results.append({"ok": False, "reason": "missing_lore_id", "entry": entry})
            continue

        existing = get_lore_entry(simulation_state, lore_id)
        if existing and existing.get("truth_status") == "true" and entry.get("truth_status") in {"false", "myth"}:
            results.append(
                {
                    "ok": False,
                    "reason": "protected_true_lore_not_overwritten",
                    "lore_id": lore_id,
                    "existing_truth_status": existing.get("truth_status"),
                    "proposed_truth_status": entry.get("truth_status"),
                }
            )
            continue

        result = upsert_lore_entry(simulation_state, entry)
        results.append(result)
        if result.get("ok"):
            lore_ids.append(lore_id)
    return {"ok": all(row.get("ok") for row in results), "results": results, "lore_ids": lore_ids}


def _import_story_arcs(
    simulation_state: Dict[str, Any],
    story_arcs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    results = []
    arc_ids = []
    for arc in story_arcs:
        arc_id = str(arc.get("arc_id") or "")
        if not arc_id:
            results.append({"ok": False, "reason": "missing_arc_id", "arc": arc})
            continue
        existing = get_story_arc(simulation_state, arc_id)
        if existing:
            # Preserve active/resolved runtime state. Only merge links/metadata by starting
            # would be too destructive, so leave existing arc alone for v1 importer.
            results.append({"ok": True, "reason": "arc_already_exists", "arc_id": arc_id, "arc": existing})
            arc_ids.append(arc_id)
            continue
        result = start_story_arc(
            simulation_state,
            arc_id,
            title=str(arc.get("title") or arc_id),
            stage=str(arc.get("stage") or "started"),
            pressure=int(arc.get("pressure") or 0),
            links={
                "lore": list(arc.get("linked_lore") or []),
                "quest": list(arc.get("linked_quests") or []),
                "puzzle": list(arc.get("linked_puzzles") or []),
                "location": list(arc.get("linked_locations") or []),
                "entity": list(arc.get("linked_entities") or []),
            },
            turn_index=int(arc.get("started_turn") or 0),
        )
        result["arc"]["status"] = arc.get("status") or result["arc"].get("status")
        result["arc"]["flags"] = dict(arc.get("flags") or {})
        result["arc"]["metadata"] = dict(arc.get("metadata") or {})
        results.append(result)
        if result.get("ok"):
            arc_ids.append(arc_id)
    return {"ok": all(row.get("ok") for row in results), "results": results, "arc_ids": arc_ids}


def _import_story_arc_milestones(
    simulation_state: Dict[str, Any],
    story_arcs: List[Dict[str, Any]],
    *,
    turn_index: int = 0,
) -> Dict[str, Any]:
    results = []
    milestone_ids = []
    for arc in story_arcs:
        arc_id = str(arc.get("arc_id") or "")
        for index, milestone in enumerate(arc.get("milestones") or []):
            if isinstance(milestone, dict):
                result = add_story_arc_milestone(
                    simulation_state,
                    arc_id=arc_id,
                    milestone_id=str(milestone.get("milestone_id") or ""),
                    title=str(milestone.get("title") or ""),
                    summary=str(milestone.get("summary") or ""),
                    objective_text=str(milestone.get("objective_text") or ""),
                    journal_on_complete=str(milestone.get("journal_on_complete") or ""),
                    quest_id=str(milestone.get("quest_id") or ""),
                    priority=int(milestone.get("priority") or 50),
                    turn_index=turn_index,
                    tags=milestone.get("tags") or [],
                    metadata={
                        "source": "story_pack_import",
                        "proposal_id": str(arc.get("proposal_id") or ""),
                        "index": index,
                    },
                )
                results.append(result)
                if result.get("ok"):
                    milestone_ids.append(str(milestone.get("milestone_id") or ""))
    return {"ok": all(row.get("ok") for row in results), "results": results, "milestone_ids": milestone_ids}


def _import_story_events(
    simulation_state: Dict[str, Any],
    story_events: List[Dict[str, Any]],
    *,
    pack_id: str,
) -> Dict[str, Any]:
    results = []
    event_ids = []
    for event in story_events:
        result = register_story_event_definition(simulation_state, event, pack_id=pack_id)
        results.append(result)
        if result.get("ok"):
            event_ids.append(str(event.get("event_id") or ""))
    return {"ok": all(row.get("ok") for row in results), "results": results, "event_ids": event_ids}


def _import_escalation_rules(
    simulation_state: Dict[str, Any],
    escalation_rules: List[Dict[str, Any]],
    *,
    pack_id: str,
) -> Dict[str, Any]:
    results = []
    rule_ids = []
    for rule in escalation_rules:
        result = register_escalation_rule_definition(simulation_state, rule, pack_id=pack_id)
        results.append(result)
        if result.get("ok"):
            rule_ids.append(str(rule.get("rule_id") or ""))
    return {"ok": all(row.get("ok") for row in results), "results": results, "rule_ids": rule_ids}


def _import_starter_quests(
    simulation_state: Dict[str, Any],
    starter_quests: List[Dict[str, Any]],
    *,
    turn_index: int,
) -> Dict[str, Any]:
    results = []
    quest_ids = []
    for transition in starter_quests:
        transition = dict(_safe_dict(transition))
        transition.setdefault("action", "start")
        result = apply_quest_transition(simulation_state, transition, turn_index=turn_index)
        results.append(result)
        if result.get("ok") and result.get("quest_id"):
            quest_ids.append(str(result.get("quest_id")))
    return {"ok": all(row.get("ok") for row in results), "results": results, "quest_ids": quest_ids}


def import_story_pack(
    simulation_state: Dict[str, Any],
    proposal: Dict[str, Any],
    *,
    turn_index: int = 0,
    starter_quests: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    validation = validate_story_proposal(simulation_state, proposal)
    if not validation.get("ok"):
        return {
            "ok": False,
            "reason": "validation_failed",
            "validation": validation,
            "pack_id": "",
            "imported": {},
        }

    normalized = validation["normalized"]
    pack_id = _stable_pack_id(normalized)
    existing = get_imported_story_pack(simulation_state, pack_id)
    if existing:
        return {
            "ok": True,
            "reason": "already_imported",
            "pack_id": pack_id,
            "idempotent": True,
            "imported": existing,
            "validation": validation,
            "results": {},
        }

    lore_result = _import_lore_entries(simulation_state, normalized.get("lore_entries") or [])
    if not lore_result.get("ok"):
        return {
            "ok": False,
            "reason": "lore_import_failed",
            "pack_id": pack_id,
            "validation": validation,
            "results": {"lore": lore_result},
        }

    arc_result = _import_story_arcs(simulation_state, normalized.get("story_arcs") or [])
    if not arc_result.get("ok"):
        return {
            "ok": False,
            "reason": "arc_import_failed",
            "pack_id": pack_id,
            "validation": validation,
            "results": {"lore": lore_result, "story_arcs": arc_result},
        }

    milestone_result = _import_story_arc_milestones(
        simulation_state,
        proposal.get("story_arcs") or [],
        turn_index=turn_index,
    )
    if not milestone_result.get("ok"):
        return {
            "ok": False,
            "reason": "milestone_import_failed",
            "pack_id": pack_id,
            "validation": validation,
            "results": {
                "lore": lore_result,
                "story_arcs": arc_result,
                "milestones": milestone_result,
            },
        }

    event_result = _import_story_events(
        simulation_state,
        normalized.get("story_events") or [],
        pack_id=pack_id,
    )
    if not event_result.get("ok"):
        return {
            "ok": False,
            "reason": "event_definition_import_failed",
            "pack_id": pack_id,
            "validation": validation,
            "results": {
                "lore": lore_result,
                "story_arcs": arc_result,
                "story_events": event_result,
            },
        }

    rule_result = _import_escalation_rules(
        simulation_state,
        normalized.get("escalation_rules") or [],
        pack_id=pack_id,
    )
    if not rule_result.get("ok"):
        return {
            "ok": False,
            "reason": "escalation_rule_import_failed",
            "pack_id": pack_id,
            "validation": validation,
            "results": {
                "lore": lore_result,
                "story_arcs": arc_result,
                "story_events": event_result,
                "escalation_rules": rule_result,
            },
        }

    quest_result = _import_starter_quests(
        simulation_state,
        starter_quests or _safe_list(_safe_dict(proposal).get("starter_quests")),
        turn_index=turn_index,
    )
    if not quest_result.get("ok"):
        return {
            "ok": False,
            "reason": "starter_quest_import_failed",
            "pack_id": pack_id,
            "validation": validation,
            "results": {
                "lore": lore_result,
                "story_arcs": arc_result,
                "story_events": event_result,
                "escalation_rules": rule_result,
                "starter_quests": quest_result,
            },
        }

    mark_result = mark_story_pack_imported(
        simulation_state,
        pack_id=pack_id,
        proposal_id=str(normalized.get("proposal_id") or ""),
        title=str(normalized.get("title") or pack_id),
        lore_ids=lore_result.get("lore_ids") or [],
        arc_ids=arc_result.get("arc_ids") or [],
        event_ids=event_result.get("event_ids") or [],
        rule_ids=rule_result.get("rule_ids") or [],
        quest_ids=quest_result.get("quest_ids") or [],
        milestone_ids=milestone_result.get("milestone_ids") or [],
        turn_index=turn_index,
        metadata={"source": "story_pack_importer_v1"},
    )
    return {
        "ok": True,
        "reason": "imported",
        "pack_id": pack_id,
        "idempotent": True,
        "validation": validation,
        "results": {
            "lore": lore_result,
            "story_arcs": arc_result,
            "milestones": milestone_result,
            "story_events": event_result,
            "escalation_rules": rule_result,
            "starter_quests": quest_result,
            "mark": mark_result,
        },
        "imported": mark_result.get("imported"),
    }
