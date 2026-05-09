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


def _next_commit_sequence(state: Dict[str, Any]) -> int:
    current = int(_safe_dict(state).get("campaign_state_commit_sequence") or 0)
    current += 1
    state["campaign_state_commit_sequence"] = current
    return current


def _current_commit_sequence(state: Dict[str, Any]) -> int:
    return int(_safe_dict(state).get("campaign_state_commit_sequence") or 0)


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


LOW_INFORMATION_LEAD_TOKENS = {
    "toward",
    "near",
    "nearby",
    "outside",
    "inside",
    "around",
    "ahead",
    "behind",
    "there",
    "here",
    "place",
    "person",
    "thing",
    "someone",
    "something",
    "lead",
    "clue",
    "trail",
    "evidence",
    "sign",
    "signs",
    "track",
    "tracks",
    "route",
    "path",
    "road",
    "area",
    "location",
    "direction",
    "matter",
    "issue",
    "problem",
    "danger",
    "trouble",
    "inspect",
    "ask",
    "follow",
    "investigate",
    "search",
    "check",
    "checking",
}


LEAD_CONNECTOR_TOKENS = {
    "the",
    "a",
    "an",
    "of",
    "to",
    "from",
    "for",
    "with",
    "and",
    "or",
    "in",
    "on",
    "at",
    "by",
    "near",
    "toward",
    "towards",
}


def _lead_label(lead: Dict[str, Any]) -> str:
    lead = _safe_dict(lead)
    return _safe_str(lead.get("name") or lead.get("title") or lead.get("label") or lead.get("id")).strip()


def _lead_content_tokens(label: str) -> List[str]:
    tokens = [
        token.strip(".,;:!?()[]{}\"'").lower()
        for token in _safe_str(label).replace("_", " ").split()
    ]
    return [
        token
        for token in tokens
        if token
        and token not in LEAD_CONNECTOR_TOKENS
        and token not in LOW_INFORMATION_LEAD_TOKENS
        and len(token) >= 3
    ]


def _is_low_information_lead_label(label: str) -> bool:
    label = " ".join(_safe_str(label).strip().split())
    if not label:
        return True
    norm = _norm(label)
    raw_tokens = [token for token in norm.split() if token]
    content_tokens = _lead_content_tokens(label)

    if len(raw_tokens) <= 1:
        return True
    if not content_tokens:
        return True
    if len(content_tokens) == 1 and content_tokens[0] in LOW_INFORMATION_LEAD_TOKENS:
        return True

    # Generic phrases like "the clue", "the evidence", "the trail" are not a
    # good handoff subject unless paired with a concrete entity/place/item.
    if len(raw_tokens) <= 3 and all(
        token in LOW_INFORMATION_LEAD_TOKENS or token in LEAD_CONNECTOR_TOKENS
        for token in raw_tokens
    ):
        return True

    return False


def _lead_specificity_score(label: str) -> int:
    label = _safe_str(label)
    content_tokens = _lead_content_tokens(label)
    raw_tokens = [token for token in _norm(label).split() if token]
    score = 0
    score += min(len(content_tokens), 6) * 10
    score += min(len(raw_tokens), 8) * 2
    if any(ch.isupper() for ch in label):
        score += 10
    if any(char.isdigit() for char in label):
        score += 5
    if len(content_tokens) >= 2:
        score += 15
    if _is_low_information_lead_label(label):
        score -= 100
    return score


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


def _objective_is_handoff_guarded(obj: Dict[str, Any], evidence: Dict[str, Any], *, current_sequence: int) -> bool:
    obj = _safe_dict(obj)
    if not bool(obj.get("handoff_objective")):
        return False

    created_sequence = int(obj.get("created_commit_sequence") or 0)
    evidence_generation = int(_safe_dict(evidence).get("generation") or 0)
    activated_after_turn = int(obj.get("activated_after_turn") or 0)
    evidence_turn = int(_safe_dict(evidence).get("turn") or 0)

    if created_sequence and evidence_generation <= created_sequence:
        return True

    if activated_after_turn and evidence_turn and evidence_turn <= activated_after_turn:
        return True

    if created_sequence and current_sequence <= created_sequence:
        return True

    return False


def _semantic_for_handoff_action(action_text: str) -> str:
    action = _norm(action_text)
    if not action:
        return ""
    if any(word in action for word in ("ask", "question", "speak", "talk")):
        return "ask_about_lead"
    if any(word in action for word in ("inspect", "examine", "look", "search")):
        return "inspect_lead"
    if any(word in action for word in ("travel", "move toward", "go to", "head to")):
        return "travel_to_lead"
    if any(word in action for word in ("follow", "track", "trail", "route")):
        return "follow_route"
    if any(word in action for word in ("journal", "notes", "objective")):
        return "consult_journal"
    if any(word in action for word in ("compare", "connect", "cross-check")):
        return "compare_evidence"
    return "investigate_lead"


def _action_mentions_lead(action_text: str, lead_label: str) -> bool:
    action_tokens = set(_lead_content_tokens(action_text))
    lead_tokens = set(_lead_content_tokens(lead_label))
    if not action_tokens or not lead_tokens:
        return False
    return bool(action_tokens & lead_tokens)


def _record_handoff_action_progress(
    state: Dict[str, Any],
    *,
    turn_record: Optional[Dict[str, Any]],
    current_sequence: int,
) -> Dict[str, Any]:
    row = _safe_dict(turn_record)
    action_text = _safe_str(row.get("player_action") or row.get("action"))
    if not action_text:
        return {"changed": False, "reason": "no_action"}

    changed = False
    progressed_objectives: List[Dict[str, Any]] = []
    turn = int(row.get("turn") or row.get("turn_index") or state.get("turn_index") or 0)
    semantic = _semantic_for_handoff_action(action_text)

    for quest_id, quest, obj in _iter_objectives(state):
        quest = _safe_dict(quest)
        obj = _safe_dict(obj)
        if not bool(obj.get("handoff_objective")) or _objective_done(obj):
            continue
        created_sequence = int(obj.get("created_commit_sequence") or 0)
        if created_sequence and current_sequence <= created_sequence:
            continue
        lead = _safe_dict(quest.get("lead") or (obj.get("known_leads") or [{}])[0])
        label = _lead_label(lead) or _safe_str(obj.get("subject") or obj.get("summary"))
        if not _action_mentions_lead(action_text, label):
            continue

        history = obj.setdefault("handoff_semantic_history", [])
        if not isinstance(history, list):
            history = []
            obj["handoff_semantic_history"] = history

        previous_semantics = {
            _safe_str(item.get("semantic"))
            for item in history
            if isinstance(item, dict)
        }
        history.append(
            {
                "turn": turn,
                "commit_sequence": current_sequence,
                "semantic": semantic,
                "action": action_text,
            }
        )
        del history[:-20]

        distinct = sorted({sem for sem in previous_semantics | {semantic} if sem})
        obj["distinct_semantic_actions"] = distinct
        obj["handoff_progress_count"] = len(distinct)
        obj["status"] = "active"
        obj["progress_evidence"] = {
            "source": "handoff_semantic_action_rotation",
            "turn": turn,
            "semantic": semantic,
            "action": action_text,
        }

        if len(distinct) >= 2:
            obj["completed"] = True
            obj["status"] = "completed"
            obj["completion_evidence"] = {
                "source": "handoff_semantic_action_rotation",
                "turn": turn,
                "distinct_semantic_actions": distinct,
            }

        progressed_objectives.append(
            {
                "quest_id": quest_id,
                "objective_id": _objective_id(obj),
                "semantic": semantic,
                "distinct_semantic_count": len(distinct),
                "completed": _objective_done(obj),
            }
        )
        changed = True

    for _quest_id, quest in _iter_quests(state):
        _sync_quest_completion(quest)

    return {
        "changed": changed,
        "reason": "handoff_progress_recorded" if changed else "no_matching_handoff_objective",
        "progressed_objectives": progressed_objectives,
    }


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
                "generation": int(row.get("generation") or row.get("commit_sequence") or 0),
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
                "generation": int(payload.get("generation") or payload.get("commit_sequence") or 0),
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
                "generation": int(row.get("campaign_state_commit_sequence") or 0),
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
                "generation": int(row.get("campaign_state_commit_sequence") or 0),
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


def reconcile_quests_from_evidence(
    state: Dict[str, Any],
    evidence: List[Dict[str, Any]],
    *,
    current_sequence: int = 0,
) -> Dict[str, Any]:
    promoted = _promote_quest_log_state_to_quest_progress(state)
    completed_updates = 0
    partial_updates = 0
    matched_evidence = 0
    guarded_handoff_evidence = 0

    for row in evidence:
        row = _safe_dict(row)
        matched_this_row = False
        for _quest_id, _quest, obj in _iter_objectives(state):
            if not _evidence_matches_objective(row, obj):
                continue
            if _objective_is_handoff_guarded(obj, row, current_sequence=current_sequence):
                guarded_handoff_evidence += 1
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
        "guarded_handoff_evidence_count": guarded_handoff_evidence,
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


def _candidate_lead_phrases_from_text(text: str) -> List[str]:
    """Extract generic concrete-ish lead phrases from deterministic text.

    This deliberately avoids scenario-specific words. It prefers multi-token
    noun-like spans and phrases after directional/result cues.
    """
    text = " ".join(_safe_str(text).replace("_", " ").replace(":", " ").split())
    if not text:
        return []

    norm = _norm(text)
    candidates: List[str] = []

    cue_phrases = (
        "points toward",
        "point toward",
        "points to",
        "point to",
        "leads toward",
        "lead toward",
        "leads to",
        "lead to",
        "indicates",
        "suggests",
        "reveals",
        "mentions",
        "names",
        "identifies",
        "connects to",
        "connected to",
        "near",
        "at",
        "in",
    )

    lowered = text.lower()
    for cue in cue_phrases:
        index = lowered.find(cue)
        if index < 0:
            continue
        after = text[index + len(cue):].strip(" .,:;!?-")
        if not after:
            continue
        words = after.split()
        for size in (5, 4, 3, 2):
            if len(words) >= size:
                phrase = " ".join(words[:size]).strip(" .,:;!?-")
                if phrase and not _is_low_information_lead_label(phrase):
                    candidates.append(phrase)
                    break

    # Also extract capitalized multi-token spans as generic entity/location/faction candidates.
    words = text.split()
    span: List[str] = []
    for word in words + [""]:
        stripped = word.strip(".,;:!?()[]{}\"'")
        if stripped[:1].isupper() and stripped.lower() not in {"i", "the", "a", "an"}:
            span.append(stripped)
            continue
        if len(span) >= 2:
            phrase = " ".join(span)
            if not _is_low_information_lead_label(phrase):
                candidates.append(phrase)
        span = []

    # Fallback: longest useful content-token phrase, but never one generic token.
    if not candidates:
        content = _lead_content_tokens(text)
        if len(content) >= 2:
            candidates.append(" ".join(content[:5]))

    deduped: List[str] = []
    seen = set()
    for phrase in candidates:
        phrase = " ".join(_safe_str(phrase).strip().split())
        key = _norm(phrase)
        if not key or key in seen or _is_low_information_lead_label(phrase):
            continue
        seen.add(key)
        deduped.append(phrase)
    deduped.sort(key=lambda phrase: -_lead_specificity_score(phrase))
    return deduped[:5]


def _lead_candidates_from_text(text: str, *, source: str, kind: str) -> List[Dict[str, Any]]:
    leads: List[Dict[str, Any]] = []
    for phrase in _candidate_lead_phrases_from_text(text):
        lead = _lead_from_text(phrase, source=source, kind=kind)
        if lead and not _is_low_information_lead_label(_lead_label(lead)):
            leads.append(lead)
    return leads


def _lead_from_text(text: str, *, source: str, kind: str = "text") -> Dict[str, Any]:
    text = _safe_str(text).strip()
    if not text:
        return {}
    cleaned = " ".join(text.replace("_", " ").replace(":", " ").split())
    if len(cleaned) > 80:
        cleaned = cleaned[:80].rsplit(" ", 1)[0]
    if _is_low_information_lead_label(cleaned):
        return {}
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
    raw_label = _lead_label(lead)
    label = _norm(raw_label)
    base += _lead_specificity_score(raw_label)
    forward_terms = (
        "points toward",
        "trail now points",
        "now points",
        "toward",
        "leads to",
        "route",
        "destination",
        "next",
        "bridge",
        "road",
        "crossing",
        "settlement",
        "camp",
        "hideout",
        "mill",
    )
    completion_terms = (
        "reported to",
        "findings were reported",
        "reported",
        "completed",
        "quest complete",
        "objective complete",
        "told bran",
        "report to",
    )

    if any(term in label for term in forward_terms):
        base += 35
    if any(term in label for term in completion_terms):
        base -= 45

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
    return max(0, base)


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
                if not _is_low_information_lead_label(_lead_label(lead)):
                    leads.append(lead)

    hook_state = _safe_dict(state.get("autoplay_story_hook_state"))
    fired_hooks = _safe_dict(hook_state.get("fired_hooks"))
    for hook_id, payload in fired_hooks.items():
        hook_id = _safe_str(hook_id)
        payload = _safe_dict(payload)
        summary = _safe_str(payload.get("summary"))
        lower = _norm(f"{hook_id} {summary}")
        is_completion_only = any(
            phrase in lower
            for phrase in (
                "reported to",
                "findings were reported",
                "objective completed",
                "quest completed",
                "completed",
                "report to bran completed",
            )
        )
        is_forward_lead = any(
            phrase in lower
            for phrase in (
                "points toward",
                "trail now points",
                "now points",
                "leads to",
                "toward the",
                "route",
                "destination",
                "bridge",
                "road",
                "camp",
                "hideout",
                "mill",
            )
        )
        if is_completion_only and not is_forward_lead:
            continue
        if any(
            term in lower
            for term in ("lead", "trail", "road", "bridge", "toward", "points", "location", "route")
        ):
            lead_text = summary or hook_id.replace("hook:", "").replace("_", " ")
            for lead in _lead_candidates_from_text(lead_text, source="autoplay_story_hook_state", kind="hook"):
                lead["hook_id"] = hook_id
                leads.append(lead)

    for row in evidence[-50:]:
        row = _safe_dict(row)
        event = _safe_dict(row.get("event"))
        for topic in _safe_list(event.get("topics")):
            topic = _safe_str(topic)
            if len(topic) >= 4:
                leads.extend(_lead_candidates_from_text(topic, source="objective_evidence", kind="topic"))
        for key in ("target", "target_name", "location", "location_name"):
            value = _safe_str(event.get(key))
            if value:
                leads.extend(_lead_candidates_from_text(value, source="objective_evidence", kind=key))
        summary = _safe_str(row.get("summary"))
        if _safe_str(row.get("source")) == "objective_progression_log" and summary:
            lead = _lead_from_text(summary, source="objective_progression_log", kind="summary")
            if lead:
                leads.append(lead)
        if summary and row.get("completed"):
            leads.extend(_lead_candidates_from_text(summary, source="completed_objective_summary", kind="summary"))

    for row in _safe_list(transcript_tail)[-12:]:
        action = _safe_str(_safe_dict(row).get("player_action") or _safe_dict(row).get("action"))
        if action:
            leads.extend(_lead_candidates_from_text(action, source="recent_action", kind="action"))

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

    deduped_by_label: Dict[str, Dict[str, Any]] = {}
    for lead in leads:
        lead = _safe_dict(lead)
        label_raw = _lead_label(lead)
        if _is_low_information_lead_label(label_raw):
            continue
        label = _norm(label_raw)
        existing = deduped_by_label.get(label)
        if not existing or _lead_priority(lead) > _lead_priority(existing):
            deduped_by_label[label] = lead
    return _sort_leads(list(deduped_by_label.values()))[:25]


HANDOFF_SEMANTIC_ACTIONS = (
    "ask_about_lead",
    "inspect_lead",
    "travel_to_lead",
    "follow_route",
    "consult_journal",
    "compare_evidence",
    "search_related_location",
    "question_related_person",
)


def _handoff_action_templates(label: str) -> List[Dict[str, str]]:
    label = _safe_str(label).strip() or "the unresolved lead"
    return [
        {
            "semantic": "ask_about_lead",
            "command": f"I ask nearby people what they know about {label}.",
        },
        {
            "semantic": "inspect_lead",
            "command": f"I inspect evidence connected to {label}, looking for concrete next steps.",
        },
        {
            "semantic": "travel_to_lead",
            "command": f"I move toward {label} and watch for signs that confirm the lead.",
        },
        {
            "semantic": "follow_route",
            "command": f"I follow the route or trail connected to {label}.",
        },
        {
            "semantic": "consult_journal",
            "command": f"I compare {label} against my journal, clues, and current objectives.",
        },
        {
            "semantic": "compare_evidence",
            "command": f"I compare the evidence around {label} with what I already know.",
        },
        {
            "semantic": "search_related_location",
            "command": f"I search the location most closely connected to {label}.",
        },
        {
            "semantic": "question_related_person",
            "command": f"I question someone connected to {label} for a specific next lead.",
        },
    ]


def _has_active_quest(state: Dict[str, Any]) -> bool:
    for _quest_id, quest in _iter_quests(state):
        if _quest_done(quest):
            continue
        if _safe_str(quest.get("status")) == "active":
            objectives = [_safe_dict(row) for row in _safe_list(quest.get("objectives"))]
            if not objectives or any(not _objective_done(obj) for obj in objectives):
                return True
    return False


def apply_generic_handoff_from_leads(
    state: Dict[str, Any],
    leads: List[Dict[str, Any]],
    *,
    current_sequence: int = 0,
    current_turn: int = 0,
) -> Dict[str, Any]:
    counts = _quest_counts(state)
    if _has_active_quest(state):
        return {"ok": True, "changed": False, "reason": "active_quest_exists", **counts}
    if counts["completed_quest_count"] <= 0:
        return {"ok": True, "changed": False, "reason": "no_completed_quest", **counts}
    if not leads:
        return {"ok": False, "changed": False, "reason": "no_unresolved_leads", **counts}

    lead = _safe_dict(leads[0])
    label = _safe_str(lead.get("name") or lead.get("title") or lead.get("id") or "unresolved lead")
    action_templates = _handoff_action_templates(label)
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
        "created_commit_sequence": int(current_sequence or 0),
        "activated_after_turn": int(current_turn or 0),
        "lead": lead,
        "objectives": [
            {
                "objective_id": objective_id,
                "summary": f"Investigate the unresolved lead: {label}.",
                "objective_type": "investigate",
                "subject": label,
                "affordance_priority": 100,
                "handoff_objective": True,
                "created_commit_sequence": int(current_sequence or 0),
                "activated_after_turn": int(current_turn or 0),
                "completion_guard": {
                    "kind": "requires_future_evidence",
                    "created_commit_sequence": int(current_sequence or 0),
                    "activated_after_turn": int(current_turn or 0),
                },
                "suggested_actions": [row["command"] for row in action_templates],
                "semantic_action_templates": action_templates,
                "handoff_semantic_history": [],
                "distinct_semantic_actions": [],
                "handoff_progress_count": 0,
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
        "created_commit_sequence": int(current_sequence or 0),
        "activated_after_turn": int(current_turn or 0),
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
        and not bool(_safe_dict(handoff).get("changed"))
        and _safe_str(_safe_dict(handoff).get("reason")) != "handoff_already_exists"
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
    current_sequence = _next_commit_sequence(state)
    current_turn = int(
        _safe_dict(turn_record).get("turn")
        or _safe_dict(turn_record).get("turn_index")
        or state.get("turn_index")
        or 0
    )

    evidence = collect_objective_evidence(
        state,
        turn_record=turn_record,
        transcript_tail=transcript_tail,
        transcript=transcript,
        phase=phase,
    )
    reconciliation = reconcile_quests_from_evidence(
        state,
        evidence,
        current_sequence=current_sequence,
    )
    leads = derive_unresolved_leads(state, evidence, transcript_tail=transcript_tail)
    if leads:
        state["unresolved_leads"] = leads[:25]
    handoff = apply_generic_handoff_from_leads(
        state,
        leads,
        current_sequence=current_sequence,
        current_turn=current_turn,
    )

    reconciliation_after_handoff = reconcile_quests_from_evidence(
        state,
        evidence,
        current_sequence=current_sequence,
    )
    handoff_progress = _record_handoff_action_progress(
        state,
        turn_record=turn_record,
        current_sequence=current_sequence,
    )
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
        "commit_sequence": current_sequence,
        "current_turn": current_turn,
        "evidence_count": len(evidence),
        "objective_evidence": evidence[-25:],
        "quest_reconciliation_summary": reconciliation,
        "quest_reconciliation_after_handoff_summary": reconciliation_after_handoff,
        "lead_summary": {
            "count": len(leads),
            "recent": leads[:10],
        },
        "handoff_summary": handoff,
        "handoff_progress_summary": handoff_progress,
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
            "commit_sequence": current_sequence,
            "current_turn": current_turn,
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