from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.player_action_context.runtime import build_player_action_context
from app.rpg.quest_log.runtime import (
    build_objective_tracker_payload,
    build_quest_log_payload,
)
from app.rpg.story_authoring.approval import (
    approve_story_proposal,
    draft_story_proposal_for_approval,
    list_pending_story_proposals,
    reject_story_proposal,
)
from app.rpg.story_packs.activation import build_story_pack_activation_snapshot

MAX_INSPECTOR_PENDING = 20
MAX_INSPECTOR_HISTORY = 20
MAX_INSPECTOR_PROPOSAL_ITEMS = 20


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _proposal_summary(proposal: Dict[str, Any]) -> Dict[str, Any]:
    proposal = _safe_dict(proposal)
    lore_entries = _safe_list(proposal.get("lore_entries"))
    story_arcs = _safe_list(proposal.get("story_arcs"))
    story_events = _safe_list(proposal.get("story_events"))
    escalation_rules = _safe_list(proposal.get("escalation_rules"))
    return {
        "proposal_id": str(proposal.get("proposal_id") or ""),
        "proposal_type": str(proposal.get("proposal_type") or ""),
        "title": str(proposal.get("title") or ""),
        "counts": {
            "lore_entries": _count(lore_entries),
            "story_arcs": _count(story_arcs),
            "story_events": _count(story_events),
            "escalation_rules": _count(escalation_rules),
        },
        "lore_entries": [
            {
                "lore_id": str(_safe_dict(row).get("lore_id") or ""),
                "title": str(_safe_dict(row).get("title") or ""),
                "truth_status": str(_safe_dict(row).get("truth_status") or "unknown"),
            }
            for row in lore_entries[:MAX_INSPECTOR_PROPOSAL_ITEMS]
            if isinstance(row, dict)
        ],
        "story_arcs": [
            {
                "arc_id": str(_safe_dict(row).get("arc_id") or ""),
                "title": str(_safe_dict(row).get("title") or ""),
                "status": str(_safe_dict(row).get("status") or ""),
                "stage": str(_safe_dict(row).get("stage") or ""),
                "pressure": int(_safe_dict(row).get("pressure") or 0),
            }
            for row in story_arcs[:MAX_INSPECTOR_PROPOSAL_ITEMS]
            if isinstance(row, dict)
        ],
        "story_events": [
            {
                "event_id": str(_safe_dict(row).get("event_id") or ""),
                "arc_id": str(_safe_dict(row).get("arc_id") or ""),
                "kind": str(_safe_dict(row).get("kind") or ""),
                "summary": str(_safe_dict(row).get("summary") or ""),
                "effect_count": _count(_safe_dict(row).get("effects")),
            }
            for row in story_events[:MAX_INSPECTOR_PROPOSAL_ITEMS]
            if isinstance(row, dict)
        ],
        "escalation_rules": [
            {
                "rule_id": str(_safe_dict(row).get("rule_id") or ""),
                "arc_id": str(_safe_dict(row).get("arc_id") or ""),
                "priority": int(_safe_dict(row).get("priority") or 0),
            }
            for row in escalation_rules[:MAX_INSPECTOR_PROPOSAL_ITEMS]
            if isinstance(row, dict)
        ],
        "bounded": {
            "max_items": MAX_INSPECTOR_PROPOSAL_ITEMS,
        },
    }


def _pending_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    row = _safe_dict(row)
    proposal = _safe_dict(row.get("proposal"))
    validation = _safe_dict(row.get("validation"))
    return {
        "pending_id": str(row.get("pending_id") or ""),
        "status": str(row.get("status") or "pending"),
        "turn_index": int(row.get("turn_index") or 0),
        "authoring_goal": str(row.get("authoring_goal") or ""),
        "proposal_id": str(row.get("proposal_id") or ""),
        "proposal_type": str(row.get("proposal_type") or ""),
        "title": str(row.get("title") or ""),
        "attempt_id": str(row.get("attempt_id") or ""),
        "validation_ok": bool(validation.get("ok")),
        "validation_errors": list(validation.get("errors") or [])[:20],
        "proposal_summary": _proposal_summary(proposal),
    }


def _history_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    row = _safe_dict(row)
    return {
        "pending_id": str(row.get("pending_id") or ""),
        "status": str(row.get("status") or "unknown"),
        "turn_index": int(row.get("turn_index") or 0),
        "reason": str(row.get("reason") or ""),
        "import_ok": bool(row.get("import_ok")),
        "imported_pack_id": str(row.get("imported_pack_id") or ""),
    }


def build_story_authoring_inspector_payload(
    simulation_state: Dict[str, Any],
    *,
    limit: int = MAX_INSPECTOR_PENDING,
) -> Dict[str, Any]:
    limit = max(0, min(MAX_INSPECTOR_PENDING, int(limit or MAX_INSPECTOR_PENDING)))
    listing = list_pending_story_proposals(simulation_state, limit=limit)
    pending = [_pending_payload(row) for row in _safe_list(listing.get("pending"))[:limit]]
    history = [_history_payload(row) for row in _safe_list(listing.get("history"))[-MAX_INSPECTOR_HISTORY:]]
    return {
        "ok": True,
        "format_version": "story_authoring_inspector_v1",
        "pending_count": int(listing.get("pending_count") or 0),
        "pending": pending,
        "history": history,
        "story_pack_activation": build_story_pack_activation_snapshot(simulation_state, limit=limit),
        "quest_log": build_quest_log_payload(simulation_state, limit=limit),
        "objective_tracker": build_objective_tracker_payload(simulation_state, limit=min(limit, 8)),
        "player_action_context": build_player_action_context(simulation_state, limit=min(limit, 12)),
        "actions": {
            "draft": "/api/rpg/story_authoring/draft",
            "pending": "/api/rpg/story_authoring/pending",
            "approve": "/api/rpg/story_authoring/approve",
            "reject": "/api/rpg/story_authoring/reject",
            "activate_pack": "/api/rpg/story_authoring/packs/activate",
            "deactivate_pack": "/api/rpg/story_authoring/packs/deactivate",
            "quest_log": "/api/rpg/quest_log/payload",
            "objective_tracker": "/api/rpg/quest_log/tracker",
            "player_action_context": "/api/rpg/player_action_context/payload",
        },
        "bounded": {
            "limit": limit,
            "max_pending": MAX_INSPECTOR_PENDING,
            "max_history": MAX_INSPECTOR_HISTORY,
            "max_proposal_items": MAX_INSPECTOR_PROPOSAL_ITEMS,
        },
        "rules": [
            "Drafting does not import.",
            "Approval imports through validator and story pack importer.",
            "Rejection never imports.",
            "The UI must not mutate story state directly.",
        ],
    }


def draft_story_authoring_inspector_proposal(
    simulation_state: Dict[str, Any],
    *,
    authoring_goal: str,
    app_context: Any = None,
    turn_index: int = 0,
    llm_text_override: Any = None,
    repair_once: bool = False,
) -> Dict[str, Any]:
    draft_result = draft_story_proposal_for_approval(
        simulation_state,
        authoring_goal=authoring_goal,
        app_context=app_context,
        turn_index=turn_index,
        llm_text_override=llm_text_override,
        repair_once=repair_once,
    )
    return {
        "ok": bool(draft_result.get("ok")),
        "reason": draft_result.get("reason"),
        "draft_result": draft_result,
        "inspector": build_story_authoring_inspector_payload(simulation_state),
    }


def approve_story_authoring_inspector_proposal(
    simulation_state: Dict[str, Any],
    *,
    pending_id: str,
    turn_index: int = 0,
    reason: str = "gm_approved",
    auto_activate: bool = False,
) -> Dict[str, Any]:
    approve_result = approve_story_proposal(
        simulation_state,
        pending_id=pending_id,
        turn_index=turn_index,
        reason=reason,
        auto_activate=auto_activate,
    )
    return {
        "ok": bool(approve_result.get("ok")),
        "reason": approve_result.get("reason"),
        "approve_result": approve_result,
        "inspector": build_story_authoring_inspector_payload(simulation_state),
    }


def reject_story_authoring_inspector_proposal(
    simulation_state: Dict[str, Any],
    *,
    pending_id: str,
    turn_index: int = 0,
    reason: str = "gm_rejected",
) -> Dict[str, Any]:
    reject_result = reject_story_proposal(
        simulation_state,
        pending_id=pending_id,
        turn_index=turn_index,
        reason=reason,
    )
    return {
        "ok": bool(reject_result.get("ok")),
        "reason": reject_result.get("reason"),
        "reject_result": reject_result,
        "inspector": build_story_authoring_inspector_payload(simulation_state),
    }