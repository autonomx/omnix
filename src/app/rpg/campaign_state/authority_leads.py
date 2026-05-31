from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Set


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


def _token_set(text: str) -> Set[str]:
    return {
        token
        for token in _norm(text).replace(":", " ").replace("_", " ").split()
        if len(token) >= 4 and token not in {"objective", "quest", "completed", "progress", "current"}
    }


def _objective_done(obj: Dict[str, Any]) -> bool:
    return bool(obj.get("completed")) or _safe_str(obj.get("status")) == "completed"


def _quest_done(quest: Dict[str, Any]) -> bool:
    return bool(quest.get("completed")) or _safe_str(quest.get("status")) == "completed"


def _quest_counts(state: Dict[str, Any]) -> Dict[str, int]:
    qp = _safe_dict(_safe_dict(state).get("quest_progress"))
    quests = _safe_dict(qp.get("quests"))
    active = completed = objectives_active = objectives_completed = 0
    for quest in quests.values():
        quest = _safe_dict(quest)
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




def _candidate_lead_phrases_from_text(text: str) -> List[str]:
    """Extract generic concrete-ish lead phrases from deterministic text.

    This deliberately avoids scenario-specific words. It prefers multi-token
    noun-like spans and phrases after directional/result cues.
    """
    text = " ".join(_safe_str(text).replace("_", " ").replace(":", " ").split())
    if not text:
        return []

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
