from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _norm(text: str) -> str:
    return " ".join(str(text or "").lower().strip().split())


def _contains_any(text: str, words: List[str]) -> bool:
    text = _norm(text)
    return any(word in text for word in words)


def _ensure_root(state: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = state.get(key)
    if not isinstance(value, dict):
        value = {}
        state[key] = value
    return value


def _ensure_arc_state(state: Dict[str, Any]) -> Dict[str, Any]:
    root = _ensure_root(state, "story_arc_state")
    root.setdefault("arcs", {})
    return root


def _ensure_milestone_state(state: Dict[str, Any]) -> Dict[str, Any]:
    root = _ensure_root(state, "story_arc_milestone_state")
    root.setdefault("arcs", {})
    return root


def _ensure_journal_state(state: Dict[str, Any]) -> Dict[str, Any]:
    root = _ensure_root(state, "campaign_journal_state")
    root.setdefault("entries", [])
    return root


def _ensure_event_queue_state(state: Dict[str, Any]) -> Dict[str, Any]:
    root = _ensure_root(state, "story_event_queue_state")
    root.setdefault("queue", [])
    return root


def _find_milestone(state: Dict[str, Any], milestone_id: str) -> Dict[str, Any] | None:
    milestone_state = _ensure_milestone_state(state)
    for arc_bucket in _safe_dict(milestone_state.get("arcs")).values():
        milestones = _safe_list(_safe_dict(arc_bucket).get("milestones"))
        for row in milestones:
            if isinstance(row, dict) and row.get("milestone_id") == milestone_id:
                return row
    return None


def _set_milestone_status(
    state: Dict[str, Any],
    *,
    milestone_id: str,
    status: str,
    turn_index: int,
) -> bool:
    row = _find_milestone(state, milestone_id)
    if not row:
        return False
    if row.get("status") == status:
        return False
    row["status"] = status
    row["updated_turn_index"] = int(turn_index)
    if status == "completed":
        row["completed_turn_index"] = int(turn_index)
    return True


def _add_milestone_once(
    state: Dict[str, Any],
    *,
    arc_id: str,
    milestone_id: str,
    title: str,
    objective_text: str,
    turn_index: int,
    priority: int = 70,
) -> bool:
    milestone_state = _ensure_milestone_state(state)
    arcs = _safe_dict(milestone_state.setdefault("arcs", {}))
    bucket = _safe_dict(arcs.setdefault(arc_id, {"arc_id": arc_id, "milestones": []}))
    milestones = _safe_list(bucket.setdefault("milestones", []))
    if any(_safe_dict(row).get("milestone_id") == milestone_id for row in milestones):
        return False
    milestones.append(
        {
            "milestone_id": milestone_id,
            "title": title,
            "objective_text": objective_text,
            "status": "active",
            "priority": int(priority),
            "created_turn_index": int(turn_index),
            "updated_turn_index": int(turn_index),
        }
    )
    bucket["milestones"] = milestones
    arcs[arc_id] = bucket
    milestone_state["arcs"] = arcs
    return True


def _set_arc_stage(
    state: Dict[str, Any],
    *,
    arc_id: str,
    stage: str,
    turn_index: int,
) -> bool:
    arc_state = _ensure_arc_state(state)
    arcs = _safe_dict(arc_state.setdefault("arcs", {}))
    arc = _safe_dict(arcs.setdefault(arc_id, {"arc_id": arc_id}))
    before = arc.get("stage")
    if before == stage:
        return False
    arc["stage"] = stage
    arc["updated_turn_index"] = int(turn_index)
    arcs[arc_id] = arc
    return True


def _append_journal_once(
    state: Dict[str, Any],
    *,
    entry_id: str,
    title: str,
    text: str,
    turn_index: int,
    tags: List[str] | None = None,
) -> bool:
    journal = _ensure_journal_state(state)
    entries = _safe_list(journal.setdefault("entries", []))
    if any(_safe_dict(row).get("entry_id") == entry_id for row in entries):
        return False
    entries.append(
        {
            "entry_id": entry_id,
            "title": title,
            "text": text,
            "turn_index": int(turn_index),
            "tags": tags or [],
        }
    )
    journal["entries"] = entries
    return True


def _queue_event_once(
    state: Dict[str, Any],
    *,
    event_id: str,
    title: str,
    summary: str,
    turn_index: int,
    severity: str = "low",
) -> bool:
    queue_state = _ensure_event_queue_state(state)
    queue = _safe_list(queue_state.setdefault("queue", []))
    if any(_safe_dict(row).get("event_id") == event_id for row in queue):
        return False
    queue.append(
        {
            "event_id": event_id,
            "title": title,
            "summary": summary,
            "turn_index": int(turn_index),
            "severity": severity,
            "source": "autoplay_story_hook",
        }
    )
    queue_state["queue"] = queue
    return True


def _mark_hook_fired(state: Dict[str, Any], hook_id: str, turn_index: int) -> None:
    root = _ensure_root(state, "autoplay_story_hook_state")
    fired = _safe_dict(root.setdefault("fired_hooks", {}))
    fired[hook_id] = {"hook_id": hook_id, "turn_index": int(turn_index)}
    root["fired_hooks"] = fired


def _hook_already_fired(state: Dict[str, Any], hook_id: str) -> bool:
    root = _safe_dict(state.get("autoplay_story_hook_state"))
    fired = _safe_dict(root.get("fired_hooks"))
    return hook_id in fired


def seed_witness_resolution_hooks(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Attach deterministic action hooks to the seeded tavern witness campaign.

    These are player-visible and test-only. They allow autoplay to prove story
    progression can occur when the LLM player takes grounded investigation
    actions. The LLM still cannot invent success; the hook decides progress.
    """
    state = simulation_state
    root = _ensure_root(state, "autoplay_story_hook_state")
    root["enabled"] = True
    root.setdefault("fired_hooks", {})
    root["hooks"] = [
        {
            "hook_id": "hook:witness:ask_bran",
            "arc_id": "arc:witness_search",
            "milestone_id": "milestone:find_witness",
            "kind": "lead_discovery",
            "description": "Asking Bran or tavern patrons about the witness reveals a cloaked traveler lead.",
            "requires_any": ["bran", "innkeeper", "patron", "traveler", "witness", "rumor"],
            "action_keywords": ["ask", "talk", "question", "rumor", "witness", "traveler"],
            "effect": {
                "journal_entry_id": "journal:witness:cloaked_traveler_lead",
                "journal_title": "A Cloaked Traveler",
                "journal_text": "Questions in the tavern point toward a cloaked traveler who may have seen what happened.",
                "arc_stage": "lead_found",
                "queue_event_id": "event:witness:lead_found",
                "queue_event_title": "Witness Lead Found",
                "queue_event_summary": "The investigation now points toward a cloaked traveler near the tavern.",
            },
        },
        {
            "hook_id": "hook:witness:inspect_tavern",
            "arc_id": "arc:witness_search",
            "milestone_id": "milestone:find_witness",
            "kind": "clue_confirmation",
            "description": "Inspecting the tavern, street, bar, or immediate surroundings confirms where the witness went.",
            "requires_any": ["tavern", "bar", "street", "outside", "surroundings", "cloak", "tracks", "clue"],
            "action_keywords": ["inspect", "look", "search", "observe", "scan", "examine", "follow"],
            "effect": {
                "journal_entry_id": "journal:witness:street_trace",
                "journal_title": "Trace Outside the Tavern",
                "journal_text": "A grounded inspection finds signs that the cloaked traveler moved toward the street outside.",
                "arc_stage": "witness_trace_found",
                "queue_event_id": "event:witness:trace_found",
                "queue_event_title": "Witness Trace Found",
                "queue_event_summary": "A clue outside the tavern narrows the search for the witness.",
            },
        },
        {
            "hook_id": "hook:witness:find_witness",
            "arc_id": "arc:witness_search",
            "milestone_id": "milestone:find_witness",
            "kind": "milestone_completion",
            "description": "Following the witness lead outside or down the street resolves the seeded witness objective.",
            "requires_any": ["street", "outside", "road", "follow", "cloaked", "traveler", "witness"],
            "action_keywords": ["follow", "approach", "find", "search", "walk", "track", "look"],
            "requires_prior_hooks_any": [
                "hook:witness:ask_bran",
                "hook:witness:inspect_tavern",
            ],
            "effect": {
                "journal_entry_id": "journal:witness:found",
                "journal_title": "Witness Found",
                "journal_text": "The search turns up the witness lead and resolves the immediate objective.",
                "arc_stage": "witness_found",
                "complete_milestone": True,
                "queue_event_id": "event:witness:found",
                "queue_event_title": "Witness Objective Resolved",
                "queue_event_summary": "The witness search objective has been resolved by a grounded investigation action.",
            },
        },
        {
            "hook_id": "hook:witness:report_to_bran",
            "arc_id": "arc:witness_search",
            "milestone_id": "milestone:report_findings_to_bran",
            "kind": "post_objective_report",
            "description": "After finding the witness lead, reporting the findings to Bran opens a response branch.",
            "requires_any": ["bran", "innkeeper", "report", "tell", "return", "findings", "witness"],
            "action_keywords": ["tell", "report", "return", "explain", "share", "ask", "talk"],
            "requires_prior_hooks_any": ["hook:witness:find_witness"],
            "effect": {
                "journal_entry_id": "journal:witness:reported_to_bran",
                "journal_title": "Reported to Bran",
                "journal_text": "The witness findings are reported back to Bran, turning the investigation toward what comes next.",
                "arc_stage": "reported_to_bran",
                "add_milestone": {
                    "milestone_id": "milestone:pursue_bandit_trail",
                    "title": "Pursue the bandit trail",
                    "objective_text": "Follow the trail suggested by the witness report.",
                    "priority": 75,
                },
                "complete_milestone": True,
                "queue_event_id": "event:witness:reported_to_bran",
                "queue_event_title": "Findings Reported",
                "queue_event_summary": "Bran now knows the witness findings and points toward a possible bandit trail.",
            },
        },
        {
            "hook_id": "hook:witness:pursue_bandit_trail",
            "arc_id": "arc:witness_search",
            "milestone_id": "milestone:pursue_bandit_trail",
            "kind": "branch_pursuit",
            "description": "Following the bandit trail after reporting to Bran advances the arc into pursuit.",
            "requires_any": ["bandit", "trail", "road", "outside", "tracks", "follow", "pursue"],
            "action_keywords": ["follow", "pursue", "track", "walk", "search", "leave", "travel"],
            "requires_prior_hooks_any": ["hook:witness:report_to_bran"],
            "effect": {
                "journal_entry_id": "journal:witness:bandit_trail",
                "journal_title": "The Bandit Trail",
                "journal_text": "The investigation branches toward a bandit trail beyond the tavern.",
                "arc_stage": "bandit_trail",
                "complete_milestone": True,
                "queue_event_id": "event:witness:bandit_trail",
                "queue_event_title": "Bandit Trail Pursued",
                "queue_event_summary": "The witness arc now points toward a bandit trail outside the tavern.",
            },
        },
    ]
    return {
        "ok": True,
        "hook_count": len(root["hooks"]),
        "hook_ids": [row["hook_id"] for row in root["hooks"]],
    }


def _hook_matches_action(
    hook: Dict[str, Any],
    *,
    player_action: str,
    state: Dict[str, Any],
) -> bool:
    text = _norm(player_action)
    if not text:
        return False

    prior_any = _safe_list(hook.get("requires_prior_hooks_any"))
    if prior_any and not any(_hook_already_fired(state, str(hook_id)) for hook_id in prior_any):
        return False

    requires_any = [str(x).lower() for x in _safe_list(hook.get("requires_any"))]
    action_keywords = [str(x).lower() for x in _safe_list(hook.get("action_keywords"))]
    if requires_any and not _contains_any(text, requires_any):
        return False
    if action_keywords and not _contains_any(text, action_keywords):
        return False
    return True


def apply_autoplay_story_hooks(
    *,
    simulation_state: Dict[str, Any],
    player_action: str,
    turn_index: int,
) -> Dict[str, Any]:
    """Apply deterministic story advancement hooks after a real turn.

    The returned state is a merged copy. Hooks are one-shot and only fire when
    their grounded trigger matches the player's action.
    """
    before_state = deepcopy(_safe_dict(simulation_state))
    state = deepcopy(before_state)
    root = _safe_dict(state.get("autoplay_story_hook_state"))
    if not root.get("enabled"):
        return {
            "ok": True,
            "changed": False,
            "fired_hooks": [],
            "simulation_state": state,
            "reason": "hooks_disabled",
        }

    fired_hooks: List[Dict[str, Any]] = []
    for hook in _safe_list(root.get("hooks")):
        hook = _safe_dict(hook)
        hook_id = _safe_str(hook.get("hook_id"))
        if not hook_id or _hook_already_fired(state, hook_id):
            continue
        if not _hook_matches_action(hook, player_action=player_action, state=state):
            continue

        effect = _safe_dict(hook.get("effect"))
        arc_id = _safe_str(hook.get("arc_id"))
        milestone_id = _safe_str(hook.get("milestone_id"))
        changed_parts: List[str] = []

        if effect.get("arc_stage") and arc_id:
            if _set_arc_stage(
                state,
                arc_id=arc_id,
                stage=_safe_str(effect.get("arc_stage")),
                turn_index=turn_index,
            ):
                changed_parts.append("arc_stage")

        if effect.get("complete_milestone") and milestone_id:
            if _set_milestone_status(
                state,
                milestone_id=milestone_id,
                status="completed",
                turn_index=turn_index,
            ):
                changed_parts.append("milestone_completed")

        add_milestone = _safe_dict(effect.get("add_milestone"))
        if add_milestone and arc_id:
            if _add_milestone_once(
                state,
                arc_id=arc_id,
                milestone_id=_safe_str(add_milestone.get("milestone_id")),
                title=_safe_str(add_milestone.get("title")),
                objective_text=_safe_str(add_milestone.get("objective_text")),
                priority=int(add_milestone.get("priority") or 70),
                turn_index=turn_index,
            ):
                changed_parts.append("milestone_added")

        if effect.get("journal_entry_id"):
            if _append_journal_once(
                state,
                entry_id=_safe_str(effect.get("journal_entry_id")),
                title=_safe_str(effect.get("journal_title")),
                text=_safe_str(effect.get("journal_text")),
                turn_index=turn_index,
                tags=["autoplay", "witness_search", _safe_str(hook.get("kind"))],
            ):
                changed_parts.append("journal_entry")

        if effect.get("queue_event_id"):
            if _queue_event_once(
                state,
                event_id=_safe_str(effect.get("queue_event_id")),
                title=_safe_str(effect.get("queue_event_title")),
                summary=_safe_str(effect.get("queue_event_summary")),
                turn_index=turn_index,
            ):
                changed_parts.append("story_event_queued")

        _mark_hook_fired(state, hook_id, turn_index)
        changed_parts.append("hook_fired")
        fired_hooks.append(
            {
                "hook_id": hook_id,
                "kind": _safe_str(hook.get("kind")),
                "changed_parts": changed_parts,
            }
        )

    return {
        "ok": True,
        "changed": bool(fired_hooks),
        "fired_hooks": fired_hooks,
        "simulation_state": state,
        "reason": "hooks_applied" if fired_hooks else "no_matching_hook",
    }


def autoplay_story_hook_player_hints(simulation_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    root = _safe_dict(simulation_state.get("autoplay_story_hook_state"))
    if not root.get("enabled"):
        return []
    hints = []
    for hook in _safe_list(root.get("hooks")):
        hook = _safe_dict(hook)
        hook_id = _safe_str(hook.get("hook_id"))
        if not hook_id or _hook_already_fired(simulation_state, hook_id):
            continue
        prior_any = _safe_list(hook.get("requires_prior_hooks_any"))
        if prior_any and not any(_hook_already_fired(simulation_state, str(hook_id)) for hook_id in prior_any):
            continue
        hints.append(
            {
                "hook_id": hook_id,
                "kind": _safe_str(hook.get("kind")),
                "description": _safe_str(hook.get("description")),
            }
        )
    return hints[:5]