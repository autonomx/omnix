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


def _award_player_xp(
    state: Dict[str, Any],
    *,
    amount: int,
    reason: str,
    turn_index: int,
) -> bool:
    if amount <= 0:
        return False
    player = _ensure_root(state, "player_state")
    before_xp = int(player.get("experience") or 0)
    before_level = int(player.get("level") or 1)
    xp_to_next = int(player.get("experience_to_next_level") or 100)
    after_xp = before_xp + int(amount)
    after_level = before_level
    while after_xp >= xp_to_next:
        after_xp -= xp_to_next
        after_level += 1
        xp_to_next = int(xp_to_next * 1.5)
    player["experience"] = after_xp
    player["level"] = after_level
    player["experience_to_next_level"] = xp_to_next
    player.setdefault("progression_log", []).append(
        {
            "turn_index": int(turn_index),
            "type": "experience",
            "amount": int(amount),
            "reason": reason,
            "level_before": before_level,
            "level_after": after_level,
        }
    )
    return True


def _update_npc_progression(
    state: Dict[str, Any],
    *,
    npc_name: str,
    trust_delta: int = 0,
    growth_stage: str = "",
    summary: str,
    turn_index: int,
) -> bool:
    if not npc_name:
        return False
    root = _ensure_root(state, "npc_progression_state")
    npcs = _safe_dict(root.setdefault("npcs", {}))
    npc = _safe_dict(npcs.setdefault(npc_name, {"name": npc_name}))
    npc["name"] = npc_name
    npc["trust"] = int(npc.get("trust") or 0) + int(trust_delta)
    if growth_stage:
        npc["growth_stage"] = growth_stage
    npc.setdefault("progression_log", []).append(
        {
            "turn_index": int(turn_index),
            "summary": summary,
            "trust_delta": int(trust_delta),
            "growth_stage": npc.get("growth_stage"),
        }
    )
    npcs[npc_name] = npc
    root["npcs"] = npcs
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
            "story_label": "Bran reveals the first witness lead",
            "story_summary": "Bran admits that a cloaked traveler left the tavern in a hurry and may have seen something important.",
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
                  "player_xp": 15,
                  "player_xp_reason": "Found the first witness lead.",
                  "npc_progression": {
                      "npc_name": "Bran",
                      "trust_delta": 1,
                      "growth_stage": "concerned_informant",
                      "summary": "Bran opens up enough to reveal the cloaked traveler lead.",
                  },
                  "display": {
                     "narration": "Bran lowers his voice and glances toward the tavern door as your question lands.",
                     "npc": {
                         "speaker": "Bran",
                         "line": "A cloaked traveler left not long ago. If they saw anything, they did not want to be noticed."
                     },
                     "summary": "Bran reveals a lead about a cloaked traveler."
                 },
             },
        },
        {
            "hook_id": "hook:witness:inspect_tavern",
            "arc_id": "arc:witness_search",
            "milestone_id": "milestone:find_witness",
            "kind": "clue_confirmation",
            "story_label": "The tavern search confirms the trail",
            "story_summary": "A closer inspection of the tavern and its exits confirms that the witness trail leads outside.",
            "description": "Inspecting the tavern, street, bar, or immediate surroundings confirms where the witness went.",
            "requires_any": ["tavern", "bar", "street", "outside", "surroundings", "cloak", "tracks", "clue"],
             "action_keywords": ["inspect", "look", "search", "observe", "scan", "examine"],
              "effect": {
                  "journal_entry_id": "journal:witness:street_trace",
                  "journal_title": "Trace Outside the Tavern",
                  "journal_text": "A grounded inspection finds signs that the cloaked traveler moved toward the street outside.",
                  "arc_stage": "witness_trace_found",
                  "queue_event_id": "event:witness:trace_found",
                  "queue_event_title": "Witness Trace Found",
                  "queue_event_summary": "A clue outside the tavern narrows the search for the witness.",
                  "player_xp": 15,
                  "player_xp_reason": "Confirmed the witness trail through investigation.",
                  "npc_progression": {
                      "npc_name": "Mira",
                      "trust_delta": 1,
                      "growth_stage": "active_observer",
                      "summary": "Mira becomes more relevant after her observations help confirm the trail.",
                  },
                  "display": {
                     "narration": "A closer look around the tavern reveals a disturbed trail near the exit.",
                     "npc": {
                         "speaker": "Mira",
                         "line": "Someone brushed past the side door in a hurry. I remember the cloak because it was travel-stained."
                     },
                     "summary": "Inspection confirms the witness trail leads outside."
                 },
             },
        },
        {
            "hook_id": "hook:witness:find_witness",
            "arc_id": "arc:witness_search",
            "milestone_id": "milestone:find_witness",
            "kind": "milestone_completion",
            "story_label": "The witness is found",
            "story_summary": "The player follows the lead and finds the cloaked traveler, resolving the immediate witness search.",
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
                  "player_xp": 30,
                  "player_xp_reason": "Resolved the immediate witness objective.",
                  "npc_progression": {
                      "npc_name": "Cloaked Traveler",
                      "trust_delta": 1,
                      "growth_stage": "revealed_witness",
                      "summary": "The cloaked traveler shifts from hidden lead to revealed witness.",
                  },
                  "display": {
                     "narration": "Following the lead brings the witness thread into focus; the immediate search is resolved.",
                     "npc": {
                         "speaker": "Cloaked Traveler",
                         "line": "I saw enough to know this was no tavern quarrel. The trail leads back toward the road."
                     },
                     "summary": "The witness is found and points toward a larger threat."
                 },
             },
        },
        {
            "hook_id": "hook:witness:report_to_bran",
            "arc_id": "arc:witness_search",
            "milestone_id": "milestone:report_findings_to_bran",
            "kind": "post_objective_report",
            "story_label": "The findings are reported to Bran",
            "story_summary": "The player returns with the witness report, and Bran connects the danger to the bandit road.",
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
                  "player_xp": 20,
                  "player_xp_reason": "Reported witness findings and opened the bandit-trail branch.",
                  "npc_progression": {
                      "npc_name": "Bran",
                      "trust_delta": 2,
                      "growth_stage": "invested_ally",
                      "summary": "Bran becomes personally invested after the witness report points toward bandit activity.",
                  },
                  "display": {
                     "narration": "Bran listens carefully, then his face hardens as the witness details fit an old fear.",
                     "npc": {
                         "speaker": "Bran",
                         "line": "That sounds like the bandit road. If they are involved, this will not end at my door."
                     },
                     "summary": "Reporting to Bran opens the bandit-trail branch."
                 },
             },
        },
        {
            "hook_id": "hook:witness:pursue_bandit_trail",
            "arc_id": "arc:witness_search",
            "milestone_id": "milestone:pursue_bandit_trail",
            "kind": "branch_pursuit",
            "story_label": "The investigation turns toward the bandit trail",
            "story_summary": "The player follows the road signs beyond the tavern, pushing the campaign toward the bandit threat.",
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
                  "player_xp": 25,
                  "player_xp_reason": "Committed to pursuing the bandit trail.",
                  "npc_progression": {
                      "npc_name": "Bran",
                      "trust_delta": 1,
                      "growth_stage": "bandit_trail_patron",
                      "summary": "Bran recognizes the player as someone willing to act on the danger beyond the tavern.",
                  },
                  "display": {
                     "narration": "The road beyond the tavern carries enough signs to turn suspicion into pursuit.",
                     "npc": {
                         "speaker": "Bran",
                         "line": "If you follow that trail, go prepared. Those men do not leave witnesses twice."
                     },
                     "summary": "The campaign branches toward the bandit trail."
                 },
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
    pre_turn_fired_hooks: set[str] | None = None,
) -> bool:
    text = _norm(player_action)
    if not text:
        return False

    prior_any = _safe_list(hook.get("requires_prior_hooks_any"))
    if prior_any and not any(str(hook_id) in (pre_turn_fired_hooks or set()) for hook_id in prior_any):
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
    pre_turn_fired_hooks = set(
        _safe_dict(_safe_dict(state.get("autoplay_story_hook_state")).get("fired_hooks")).keys()
    )

    fired_hooks: List[Dict[str, Any]] = []
    for hook in _safe_list(root.get("hooks")):
        hook = _safe_dict(hook)
        hook_id = _safe_str(hook.get("hook_id"))
        if not hook_id or _hook_already_fired(state, hook_id):
            continue
        if not _hook_matches_action(
            hook,
            player_action=player_action,
            state=state,
            pre_turn_fired_hooks=pre_turn_fired_hooks,
        ):
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

        if _award_player_xp(
            state,
            amount=int(effect.get("player_xp") or 0),
            reason=_safe_str(effect.get("player_xp_reason")),
            turn_index=turn_index,
        ):
            changed_parts.append("player_xp")

        npc_progression = _safe_dict(effect.get("npc_progression"))
        if npc_progression:
            if _update_npc_progression(
                state,
                npc_name=_safe_str(npc_progression.get("npc_name")),
                trust_delta=int(npc_progression.get("trust_delta") or 0),
                growth_stage=_safe_str(npc_progression.get("growth_stage")),
                summary=_safe_str(npc_progression.get("summary")),
                turn_index=turn_index,
            ):
                changed_parts.append("npc_progression")

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
                "story_label": _safe_str(hook.get("story_label")),
                "story_summary": _safe_str(hook.get("story_summary")),
                "kind": _safe_str(hook.get("kind")),
                "changed_parts": changed_parts,
                "display": _safe_dict(effect.get("display")),
            }
        )
        break

    display_payloads = [
        _safe_dict(row.get("display"))
        for row in fired_hooks
        if _safe_dict(row.get("display"))
    ]
    primary_display = display_payloads[-1] if display_payloads else {}

    return {
        "ok": True,
        "changed": bool(fired_hooks),
        "fired_hooks": fired_hooks,
        "display": primary_display,
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