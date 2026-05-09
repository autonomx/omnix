from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _norm(value: Any) -> str:
    return " ".join(_safe_str(value).lower().strip().split())


def _stable_id(prefix: str, text: str) -> str:
    digest = hashlib.sha1(_safe_str(text).encode("utf-8")).hexdigest()[:10]
    return f"{prefix}:{digest}"


def _bounded_append(state: Dict[str, Any], key: str, row: Dict[str, Any], *, limit: int = 100) -> None:
    log = state.setdefault(key, [])
    if isinstance(log, list):
        log.append(row)
        del log[:-limit]


def _quest_progress(state: Dict[str, Any]) -> Dict[str, Any]:
    state = _safe_dict(state)
    qp = state.setdefault("quest_progress", {})
    if not isinstance(qp, dict):
        qp = {}
        state["quest_progress"] = qp
    quests = qp.setdefault("quests", {})
    if not isinstance(quests, dict):
        quests = {}
        qp["quests"] = quests
    return qp


def _iter_quests(state: Dict[str, Any]) -> Iterable[Tuple[str, Dict[str, Any]]]:
    quests = _safe_dict(_quest_progress(state).get("quests"))
    for quest_id, quest in quests.items():
        yield _safe_str(quest_id), _safe_dict(quest)


def _iter_objectives(state: Dict[str, Any]) -> Iterable[Tuple[str, Dict[str, Any], Dict[str, Any]]]:
    for quest_id, quest in _iter_quests(state):
        for obj in _safe_list(quest.get("objectives")):
            yield quest_id, quest, _safe_dict(obj)


def _promote_quest_log_state_to_quest_progress(state: Dict[str, Any]) -> int:
    qp_quests = _safe_dict(_quest_progress(state).get("quests"))
    ql_quests = _safe_dict(_safe_dict(state.get("quest_log_state")).get("quests"))
    changed = 0
    for quest_id, quest in ql_quests.items():
        if quest_id not in qp_quests:
            qp_quests[quest_id] = dict(_safe_dict(quest))
            changed += 1
    return changed


def _objective_id(obj: Dict[str, Any]) -> str:
    return _safe_str(obj.get("objective_id") or obj.get("id") or obj.get("milestone_id"))


def _objective_text(obj: Dict[str, Any]) -> str:
    return _safe_str(
        obj.get("summary")
        or obj.get("objective_text")
        or obj.get("title")
        or obj.get("description")
    )


def _objective_done(obj: Dict[str, Any]) -> bool:
    return bool(obj.get("completed")) or _safe_str(obj.get("status")) == "completed"


def _quest_done(quest: Dict[str, Any]) -> bool:
    return bool(quest.get("completed")) or _safe_str(quest.get("status")) == "completed"


def _mark_objective_completed(obj: Dict[str, Any], evidence: Dict[str, Any]) -> bool:
    before = _objective_done(obj)
    obj["completed"] = True
    obj["status"] = "completed"
    obj["completion_evidence"] = {
        "source": _safe_str(evidence.get("source")),
        "summary": _safe_str(evidence.get("summary")),
        "turn": evidence.get("turn"),
    }
    return not before


def _mark_objective_progressed(obj: Dict[str, Any], evidence: Dict[str, Any]) -> bool:
    if _objective_done(obj):
        return False
    before = int(obj.get("progress_count") or 0)
    obj["progress_count"] = max(before, 1)
    obj["status"] = _safe_str(obj.get("status") or "active")
    obj["progress_evidence"] = {
        "source": _safe_str(evidence.get("source")),
        "summary": _safe_str(evidence.get("summary")),
        "turn": evidence.get("turn"),
    }
    return before <= 0


def _sync_quest_completion(quest: Dict[str, Any]) -> bool:
    objectives = [_safe_dict(row) for row in _safe_list(quest.get("objectives"))]
    if not objectives:
        return False
    all_done = all(_objective_done(obj) for obj in objectives)
    before = _quest_done(quest)
    if all_done:
        quest["completed"] = True
        quest["status"] = "completed"
    elif not before:
        quest["completed"] = False
        quest["status"] = _safe_str(quest.get("status") or "active")
    return all_done and not before


def _token_set(text: str) -> Set[str]:
    return {
        token
        for token in _norm(text).replace(":", " ").replace("_", " ").split()
        if len(token) >= 4 and token not in {"objective", "quest", "completed", "progress", "current"}
    }


def _evidence_matches_objective(evidence: Dict[str, Any], obj: Dict[str, Any]) -> bool:
    evidence_obj_id = _safe_str(evidence.get("objective_id"))
    if evidence_obj_id and evidence_obj_id == _objective_id(obj):
        return True

    evidence_text = _safe_str(evidence.get("summary") or evidence.get("text") or evidence.get("hook_id"))
    obj_text = _objective_text(obj)
    if not evidence_text or not obj_text:
        return False

    ev_tokens = _token_set(evidence_text)
    obj_tokens = _token_set(obj_text)
    if not ev_tokens or not obj_tokens:
        return False

    overlap = ev_tokens & obj_tokens
    return len(overlap) >= 2 or (len(obj_tokens) <= 3 and bool(overlap))


def _collect_evidence_from_progression_log(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    for row in _safe_list(state.get("objective_progression_log"))[-100:]:
        row = _safe_dict(row)
        if not row.get("matched"):
            continue
        evidence.append(
            {
                "source": "objective_progression_log",
                "objective_id": _safe_str(row.get("objective_id") or row.get("id")),
                "quest_id": _safe_str(row.get("quest_id")),
                "completed": bool(row.get("completed")) or _safe_str(row.get("status")) == "completed",
                "partial": bool(row.get("partial")) or int(row.get("progress_count") or 0) > 0,
                "summary": _safe_str(row.get("summary")),
                "event": _safe_dict(row.get("event")),
                "turn": row.get("turn"),
                "raw": row,
            }
        )
    return evidence


def _collect_evidence_from_hooks(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    hook_state = _safe_dict(state.get("autoplay_story_hook_state"))
    fired_hooks = _safe_dict(hook_state.get("fired_hooks"))
    for hook_id, payload in fired_hooks.items():
        hook_id = _safe_str(hook_id)
        payload = _safe_dict(payload)
        lower = _norm(hook_id + " " + _safe_str(payload.get("summary")))
        if not (
            hook_id.startswith("hook:objective")
            or "objective" in lower
            or "completed" in lower
            or "progress" in lower
        ):
            continue
        completed = "completed" in lower or payload.get("completed") is True
        partial = "progress" in lower or payload.get("partial") is True or not completed
        evidence.append(
            {
                "source": "autoplay_story_hook_state",
                "hook_id": hook_id,
                "objective_id": _safe_str(payload.get("objective_id") or payload.get("id")),
                "quest_id": _safe_str(payload.get("quest_id")),
                "completed": completed,
                "partial": partial,
                "summary": _safe_str(payload.get("summary") or hook_id.replace("hook:", "").replace("_", " ")),
                "turn": payload.get("turn"),
                "raw": payload,
            }
        )
    return evidence


def _collect_evidence_from_turn_record(turn_record: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    row = _safe_dict(turn_record)
    if not row:
        return []
    evidence: List[Dict[str, Any]] = []
    progression = _safe_dict(row.get("objective_progression"))
    for completed in _safe_list(progression.get("completed_objectives")):
        completed = _safe_dict(completed)
        evidence.append(
            {
                "source": "turn_record.objective_progression.completed",
                "objective_id": _safe_str(completed.get("objective_id") or completed.get("id")),
                "quest_id": _safe_str(completed.get("quest_id")),
                "completed": True,
                "partial": False,
                "summary": _safe_str(completed.get("summary")),
                "turn": row.get("turn") or row.get("turn_index"),
                "raw": completed,
            }
        )
    for progressed in _safe_list(progression.get("progressed_objectives")):
        progressed = _safe_dict(progressed)
        evidence.append(
            {
                "source": "turn_record.objective_progression.progressed",
                "objective_id": _safe_str(progressed.get("objective_id") or progressed.get("id")),
                "quest_id": _safe_str(progressed.get("quest_id")),
                "completed": False,
                "partial": True,
                "summary": _safe_str(progressed.get("summary")),
                "turn": row.get("turn") or row.get("turn_index"),
                "raw": progressed,
            }
        )
    return evidence


def _collect_evidence_from_transcript(transcript: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    for row in _safe_list(transcript):
        evidence.extend(_collect_evidence_from_turn_record(_safe_dict(row)))
    return evidence


def collect_objective_evidence(
    state: Dict[str, Any],
    *,
    turn_record: Optional[Dict[str, Any]] = None,
    transcript_tail: Optional[List[Dict[str, Any]]] = None,
    transcript: Optional[List[Dict[str, Any]]] = None,
    phase: str = "turn",
) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    evidence.extend(_collect_evidence_from_progression_log(state))
    evidence.extend(_collect_evidence_from_hooks(state))
    evidence.extend(_collect_evidence_from_turn_record(turn_record))
    evidence.extend(_collect_evidence_from_transcript(transcript_tail))
    if phase == "final":
        evidence.extend(_collect_evidence_from_transcript(transcript))

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for row in evidence:
        row = _safe_dict(row)
        key = (
            _safe_str(row.get("source")),
            _safe_str(row.get("objective_id")),
            _safe_str(row.get("summary")),
            bool(row.get("completed")),
            bool(row.get("partial")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped[-200:]


def reconcile_quests_from_evidence(state: Dict[str, Any], evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
    promoted = _promote_quest_log_state_to_quest_progress(state)
    completed_updates = 0
    partial_updates = 0
    matched_evidence = 0

    for row in evidence:
        row = _safe_dict(row)
        matched_this_row = False
        for _quest_id, _quest, obj in _iter_objectives(state):
            if not _evidence_matches_objective(row, obj):
                continue
            matched_this_row = True
            if row.get("completed"):
                if _mark_objective_completed(obj, row):
                    completed_updates += 1
            elif row.get("partial"):
                if _mark_objective_progressed(obj, row):
                    partial_updates += 1
        if matched_this_row:
            matched_evidence += 1

    quests_completed = 0
    for _quest_id, quest in _iter_quests(state):
        if _sync_quest_completion(quest):
            quests_completed += 1

    summary = {
        "ok": True,
        "evidence_count": len(evidence),
        "matched_evidence_count": matched_evidence,
        "quest_promotions": promoted,
        "completed_objective_updates": completed_updates,
        "partial_objective_updates": partial_updates,
        "quests_completed": quests_completed,
    }
    _bounded_append(state, "quest_reconciliation_log", summary, limit=100)
    _bounded_append(state, "campaign_state_commit_reconciliation_log", summary, limit=100)
    return summary


def _quest_counts(state: Dict[str, Any]) -> Dict[str, int]:
    active = 0
    completed = 0
    objectives_active = 0
    objectives_completed = 0
    for _quest_id, quest in _iter_quests(state):
        if _quest_done(quest):
            completed += 1
        elif _safe_str(quest.get("status")) == "active":
            active += 1
        for obj in _safe_list(quest.get("objectives")):
            obj = _safe_dict(obj)
            if _objective_done(obj):
                objectives_completed += 1
            else:
                objectives_active += 1
    return {
        "active_quest_count": active,
        "completed_quest_count": completed,
        "active_objective_count": objectives_active,
        "completed_objective_count": objectives_completed,
    }


def _lead_from_text(text: str, *, source: str, kind: str = "text") -> Dict[str, Any]:
    text = _safe_str(text).strip()
    if not text:
        return {}
    cleaned = " ".join(text.replace("_", " ").replace(":", " ").split())
    if len(cleaned) > 80:
        cleaned = cleaned[:80].rsplit(" ", 1)[0]
    return {
        "id": _stable_id(f"lead:{source}", cleaned),
        "name": cleaned,
        "source": source,
        "kind": kind,
    }


LEAD_SOURCE_PRIORITY = {
    "explicit": 100,
    "known_leads": 100,
    "unresolved_leads": 100,
    "quest_leads": 95,
    "story_leads": 95,
    "autoplay_story_hook_state": 90,
    "objective_evidence": 85,
    "objective_progression_log": 85,
    "completed_objective_summary": 75,
    "scene": 50,
    "location_history": 45,
    "recent_action": 20,
    "generic_local_fallback": 10,
}


def _lead_priority(lead: Dict[str, Any]) -> int:
    lead = _safe_dict(lead)
    source = _safe_str(lead.get("source"))
    kind = _safe_str(lead.get("kind"))
    base = int(LEAD_SOURCE_PRIORITY.get(source, 25))
    label = _norm(lead.get("name") or lead.get("title") or lead.get("id"))

    repeated_action_terms = {
        "inspect",
        "checking",
        "nearby",
        "fresh",
        "tracks",
        "wagon",
        "ruts",
        "cord",
        "cloth",
        "markings",
        "signs",
    }
    action_term_count = len(set(label.split()) & repeated_action_terms)
    if source == "recent_action":
        base -= min(15, action_term_count * 2)

    if kind in {"hook", "fact", "topic", "target", "location"}:
        base += 5
    return base


def _sort_leads(leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for index, lead in enumerate(leads):
        lead = dict(_safe_dict(lead))
        lead.setdefault("priority", _lead_priority(lead))
        lead.setdefault("rank_index", index)
        enriched.append(lead)
    enriched.sort(
        key=lambda row: (
            -int(row.get("priority") or 0),
            int(row.get("rank_index") or 0),
        )
    )
    return enriched


def derive_unresolved_leads(
    state: Dict[str, Any],
    evidence: List[Dict[str, Any]],
    *,
    transcript_tail: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    leads: List[Dict[str, Any]] = []

    for key in ("known_leads", "unresolved_leads", "quest_leads", "story_leads"):
        for row in _safe_list(state.get(key)):
            lead = dict(row) if isinstance(row, dict) else {"name": _safe_str(row)}
            if lead.get("resolved") or _safe_str(lead.get("status")) == "completed":
                continue
            if _safe_str(lead.get("name") or lead.get("title") or lead.get("id")):
                lead.setdefault("source", key)
                lead.setdefault("kind", "explicit")
                leads.append(lead)

    hook_state = _safe_dict(state.get("autoplay_story_hook_state"))
    fired_hooks = _safe_dict(hook_state.get("fired_hooks"))
    for hook_id, payload in fired_hooks.items():
        hook_id = _safe_str(hook_id)
        payload = _safe_dict(payload)
        summary = _safe_str(payload.get("summary"))
        lower = _norm(f"{hook_id} {summary}")
        if any(
            term in lower
            for term in ("lead", "trail", "road", "bridge", "toward", "points", "location", "route")
        ):
            lead_text = summary or hook_id.replace("hook:", "").replace("_", " ")
            lead = _lead_from_text(lead_text, source="autoplay_story_hook_state", kind="hook")
            if lead:
                lead["hook_id"] = hook_id
                leads.append(lead)

    for row in evidence[-50:]:
        row = _safe_dict(row)
        event = _safe_dict(row.get("event"))
        for topic in _safe_list(event.get("topics")):
            topic = _safe_str(topic)
            if len(topic) >= 4:
                lead = _lead_from_text(topic, source="objective_evidence", kind="topic")
                if lead:
                    leads.append(lead)
        for key in ("target", "target_name", "location", "location_name"):
            value = _safe_str(event.get(key))
            if value:
                lead = _lead_from_text(value, source="objective_evidence", kind=key)
                if lead:
                    leads.append(lead)
        summary = _safe_str(row.get("summary"))
        if _safe_str(row.get("source")) == "objective_progression_log" and summary:
            lead = _lead_from_text(summary, source="objective_progression_log", kind="summary")
            if lead:
                leads.append(lead)
        if summary and row.get("completed"):
            tokens = list(_token_set(summary))
            if tokens:
                lead = _lead_from_text(" ".join(tokens[:6]), source="completed_objective_summary", kind="summary")
                if lead:
                    leads.append(lead)

    for row in _safe_list(transcript_tail)[-12:]:
        action = _safe_str(_safe_dict(row).get("player_action") or _safe_dict(row).get("action"))
        if action:
            tokens = list(_token_set(action))
            if tokens:
                lead = _lead_from_text(" ".join(tokens[:8]), source="recent_action", kind="action")
                if lead:
                    leads.append(lead)

    scene = _safe_dict(state.get("scene"))
    scene_label = _safe_str(
        state.get("current_location_name")
        or scene.get("location")
        or scene.get("name")
        or state.get("current_location")
    )
    if scene_label:
        lead = _lead_from_text(scene_label, source="scene", kind="location")
        if lead:
            leads.append(lead)

    counts = _quest_counts(state)
    if not leads and counts["completed_quest_count"] > 0:
        label = scene_label or "the current area"
        leads.append(
            {
                "id": _stable_id("lead:local_unresolved", label),
                "name": f"unresolved trouble near {label}",
                "source": "generic_local_fallback",
                "kind": "local_investigation",
            }
        )

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for lead in leads:
        lead = _safe_dict(lead)
        label = _norm(lead.get("name") or lead.get("title") or lead.get("id"))
        if not label or label in seen:
            continue
        seen.add(label)
        deduped.append(lead)
    return _sort_leads(deduped)[:25]


def _has_active_quest(state: Dict[str, Any]) -> bool:
    for _quest_id, quest in _iter_quests(state):
        if _quest_done(quest):
            continue
        if _safe_str(quest.get("status")) == "active":
            objectives = [_safe_dict(row) for row in _safe_list(quest.get("objectives"))]
            if not objectives or any(not _objective_done(obj) for obj in objectives):
                return True
    return False


def apply_generic_handoff_from_leads(state: Dict[str, Any], leads: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = _quest_counts(state)
    if _has_active_quest(state):
        return {"ok": True, "changed": False, "reason": "active_quest_exists", **counts}
    if counts["completed_quest_count"] <= 0:
        return {"ok": True, "changed": False, "reason": "no_completed_quest", **counts}
    if not leads:
        return {"ok": False, "changed": False, "reason": "no_unresolved_leads", **counts}

    lead = _safe_dict(leads[0])
    label = _safe_str(lead.get("name") or lead.get("title") or lead.get("id") or "unresolved lead")
    quest_id = _stable_id("quest:investigate_lead", label)
    objective_id = _stable_id("objective:investigate_lead", label)
    quests = _safe_dict(_quest_progress(state).get("quests"))
    if quest_id in quests:
        quest = _safe_dict(quests[quest_id])
        if not _quest_done(quest):
            quest["status"] = "active"
        return {"ok": True, "changed": False, "reason": "handoff_already_exists", "quest_id": quest_id, **counts}

    quests[quest_id] = {
        "quest_id": quest_id,
        "title": f"Investigate Lead: {label}",
        "status": "active",
        "completed": False,
        "source": "campaign_state_authority_commit",
        "priority": 100,
        "handoff_quest": True,
        "lead": lead,
        "objectives": [
            {
                "objective_id": objective_id,
                "summary": f"Investigate the unresolved lead: {label}.",
                "objective_type": "investigate",
                "subject": label,
                "affordance_priority": 100,
                "handoff_objective": True,
                "suggested_actions": [
                    f"I follow up on the lead: {label}.",
                    f"I ask nearby people what they know about {label}.",
                    f"I inspect the place or evidence connected to {label}.",
                ],
                "status": "active",
                "completed": False,
                "known_leads": [lead],
                "completion_rules": [
                    {
                        "semantic_actions": ["inspect", "travel", "ask", "follow"],
                        "topics": [token for token in _token_set(label)],
                    }
                ],
            }
        ],
    }
    row = {
        "quest_id": quest_id,
        "objective_id": objective_id,
        "lead": lead,
        "summary": f"Activated generic investigation quest for unresolved lead: {label}.",
        "source": "campaign_state_authority_commit",
    }
    _bounded_append(state, "quest_handoff_log", row, limit=100)
    _bounded_append(state, "campaign_state_commit_handoff_log", row, limit=100)
    return {
        "ok": True,
        "changed": True,
        "reason": "generic_handoff_created",
        "quest_id": quest_id,
        "objective_id": objective_id,
        **_quest_counts(state),
    }


def _quest_progress_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    quests_out: List[Dict[str, Any]] = []
    active_count = 0
    completed_count = 0
    total_objectives = 0
    completed_objectives = 0
    for quest_id, quest in _iter_quests(state):
        objectives = []
        for obj in _safe_list(quest.get("objectives")):
            obj = _safe_dict(obj)
            done = _objective_done(obj)
            total_objectives += 1
            completed_objectives += 1 if done else 0
            objectives.append(
                {
                    "objective_id": _objective_id(obj),
                    "summary": _objective_text(obj),
                    "status": "completed" if done else _safe_str(obj.get("status") or "active"),
                    "completed": done,
                    "subject": _safe_str(obj.get("subject")),
                    "handoff_objective": bool(obj.get("handoff_objective")),
                    "affordance_priority": int(obj.get("affordance_priority") or 0),
                    "suggested_actions": _safe_list(obj.get("suggested_actions")),
                }
            )
        done = _quest_done(quest)
        completed_count += 1 if done else 0
        active_count += 0 if done else 1 if _safe_str(quest.get("status")) == "active" else 0
        quests_out.append(
            {
                "quest_id": quest_id,
                "title": _safe_str(quest.get("title") or quest_id),
                "status": "completed" if done else _safe_str(quest.get("status") or "active"),
                "completed": done,
                "objectives": objectives,
                "completed_objective_count": sum(1 for obj in objectives if obj["completed"]),
                "objective_count": len(objectives),
                "source": _safe_str(quest.get("source")),
                "priority": int(quest.get("priority") or 0),
                "handoff_quest": bool(quest.get("handoff_quest")),
                "lead": _safe_dict(quest.get("lead")),
            }
        )
    return {
        "source": "campaign_state_authority_commit.quest_progress",
        "quest_count": len(quests_out),
        "active_count": active_count,
        "completed_count": completed_count,
        "objective_count": total_objectives,
        "completed_objective_count": completed_objectives,
        "quests": quests_out,
    }


def _stale_state_summary(state: Dict[str, Any], evidence: List[Dict[str, Any]], handoff: Dict[str, Any]) -> Dict[str, Any]:
    counts = _quest_counts(state)
    completed_evidence_count = sum(1 for row in evidence if _safe_dict(row).get("completed"))
    stale_active_objectives = []
    for quest_id, quest, obj in _iter_objectives(state):
        if _objective_done(obj):
            continue
        for row in evidence:
            if row.get("completed") and _evidence_matches_objective(row, obj):
                stale_active_objectives.append(
                    {
                        "quest_id": quest_id,
                        "objective_id": _objective_id(obj),
                        "summary": _objective_text(obj),
                        "evidence_source": _safe_str(row.get("source")),
                    }
                )
                break
    completed_without_next = (
        counts["completed_quest_count"] > 0
        and counts["active_quest_count"] <= 0
        and not _safe_dict(handoff).get("changed")
    )
    return {
        "ok": not stale_active_objectives and not completed_without_next,
        "stale_active_objectives": stale_active_objectives,
        "completed_evidence_count": completed_evidence_count,
        "completed_without_next_objective": completed_without_next,
        **counts,
    }


def commit_campaign_state(
    runtime_state: Dict[str, Any],
    *,
    turn_record: Optional[Dict[str, Any]] = None,
    transcript_tail: Optional[List[Dict[str, Any]]] = None,
    transcript: Optional[List[Dict[str, Any]]] = None,
    phase: str = "turn",
    performance_budget_ms: int = 25,
) -> Dict[str, Any]:
    """Commit campaign state into one canonical, deterministic state.

    Per-turn mode is bounded and should only receive current turn/tail.
    Final mode may receive full transcript for reporting consistency.
    """
    start = time.perf_counter()
    state = _safe_dict(runtime_state)
    phase = "final" if phase == "final" else "turn"

    evidence = collect_objective_evidence(
        state,
        turn_record=turn_record,
        transcript_tail=transcript_tail,
        transcript=transcript,
        phase=phase,
    )
    reconciliation = reconcile_quests_from_evidence(state, evidence)
    leads = derive_unresolved_leads(state, evidence, transcript_tail=transcript_tail)
    if leads:
        state["unresolved_leads"] = leads[:25]
    handoff = apply_generic_handoff_from_leads(state, leads)

    reconciliation_after_handoff = reconcile_quests_from_evidence(state, evidence)
    quest_summary = _quest_progress_summary(state)
    stale_state = _stale_state_summary(state, evidence, handoff)

    elapsed_ms = int(round((time.perf_counter() - start) * 1000))
    perf = {
        "ok": elapsed_ms <= int(performance_budget_ms or 25) if phase == "turn" else elapsed_ms <= 1000,
        "elapsed_ms": elapsed_ms,
        "budget_ms": int(performance_budget_ms or 25) if phase == "turn" else 1000,
        "phase": phase,
    }

    commit_summary = {
        "ok": bool(reconciliation.get("ok", True)) and bool(handoff.get("ok", True)) and bool(stale_state.get("ok", True)),
        "phase": phase,
        "evidence_count": len(evidence),
        "objective_evidence": evidence[-25:],
        "quest_reconciliation_summary": reconciliation,
        "quest_reconciliation_after_handoff_summary": reconciliation_after_handoff,
        "lead_summary": {
            "count": len(leads),
            "recent": leads[:10],
        },
        "handoff_summary": handoff,
        "quest_progress_summary": quest_summary,
        "stale_state_summary": stale_state,
        "performance": perf,
    }
    _bounded_append(
        state,
        "campaign_state_commit_log",
        {
            "phase": phase,
            "ok": commit_summary["ok"],
            "elapsed_ms": elapsed_ms,
            "evidence_count": len(evidence),
            "handoff_changed": bool(handoff.get("changed")),
            "stale_ok": bool(stale_state.get("ok")),
        },
        limit=100,
    )
    state["campaign_state_commit_summary"] = commit_summary
    return {
        "ok": commit_summary["ok"],
        "state": state,
        "summary": commit_summary,
    }