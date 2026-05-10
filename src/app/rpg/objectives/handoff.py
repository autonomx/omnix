from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List

from app.rpg.objectives.reconciliation import (
    reconcile_objective_progression_into_quests,
)


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


def _lead_label(lead: Dict[str, Any]) -> str:
    return _safe_str(
        lead.get("name")
        or lead.get("title")
        or lead.get("label")
        or lead.get("location")
        or lead.get("npc")
        or lead.get("item")
        or lead.get("subject")
        or lead.get("id")
    ).strip()


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


def _action_lead_phrases(text: str) -> List[str]:
    lower = _norm(text)
    phrases: List[str] = []
    patterns = (
        r"(?:toward|to|at|near|outside|inside|along)\s+(?:the\s+)?([a-z][a-z0-9' -]{3,50})",
        r"(?:tracks|trail|markings|signs|ruts|cord|cloth|prints)\s+(?:near|toward|to|at|outside|inside)?\s*(?:the\s+)?([a-z][a-z0-9' -]{3,50})",
        r"(?:ask|warn|find|follow|inspect|search)\s+(?:the\s+)?([a-z][a-z0-9' -]{3,50})",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, lower):
            phrase = match.group(1).strip(" .,;:!?")
            if phrase and phrase not in phrases:
                phrases.append(phrase)
    return phrases[:8]


def _iter_unresolved_leads(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    state = _safe_dict(state)
    leads: List[Dict[str, Any]] = []

    for key in ("known_leads", "unresolved_leads", "quest_leads", "story_leads"):
        for row in _safe_list(state.get(key)):
            if isinstance(row, dict):
                lead = dict(row)
            else:
                lead = {"name": _safe_str(row)}
            if lead.get("resolved") or _safe_str(lead.get("status")) == "completed":
                continue
            if _lead_label(lead):
                leads.append(lead)

    # Objective progression events often contain the most recent actionable
    # nouns/topics even when the scenario did not maintain explicit lead lists.
    for row in _safe_list(state.get("objective_progression_log")):
        row = _safe_dict(row)
        event = _safe_dict(row.get("event"))
        for topic in _safe_list(event.get("topics")):
            topic = _safe_str(topic).strip()
            if len(topic) >= 4 and topic not in {"objective", "current", "progress", "specific", "concrete"}:
                lead = _lead_from_text(topic, source="objective_progression_log", kind="topic")
                if lead:
                    leads.append(lead)
        target = _safe_str(event.get("target") or event.get("target_name"))
        if target:
            lead = _lead_from_text(target, source="objective_progression_log", kind="target")
            if lead:
                leads.append(lead)
        location = _safe_str(event.get("location_name") or event.get("location"))
        if location:
            lead = _lead_from_text(location, source="objective_progression_log", kind="location")
            if lead:
                leads.append(lead)

    # Recent actions can reveal unresolved people/places/items after a quest
    # completes. This stays generic by extracting phrases rather than checking
    # scenario-specific names.
    for row in _safe_list(state.get("recent_turns") or state.get("transcript_tail") or state.get("action_history")):
        action = _safe_str(_safe_dict(row).get("player_action") or _safe_dict(row).get("action"))
        for phrase in _action_lead_phrases(action):
            lead = _lead_from_text(phrase, source="recent_actions", kind="action_phrase")
            if lead:
                leads.append(lead)

    # Location history and current scene provide a fallback investigation lead.
    for row in _safe_list(state.get("location_history")):
        row = _safe_dict(row)
        label = _safe_str(row.get("name") or row.get("location_id"))
        if label:
            lead = _lead_from_text(label, source="location_history", kind="location")
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

    # Generic facts can also produce unresolved leads. Include legacy fact bags,
    # but treat them through generic key/value extraction.
    for fact_root in (
        "objective_facts",
        "world_facts",
        "story_facts",
        "scenario_facts",
        "quest_facts",
        "witness_search_facts",
        "bandit_road_facts",
    ):
        facts = _safe_dict(state.get(fact_root))
        for key, value in facts.items():
            if not value:
                continue
            key_text = _safe_str(key)
            value_text = _safe_str(value if isinstance(value, str) else "")
            if any(term in key_text for term in ("lead", "trail", "location", "place", "person", "npc", "item", "tracks", "signs", "route", "door", "mark", "danger")):
                leads.append(
                    {
                        "id": f"{fact_root}:{key_text}",
                        "name": value_text or key_text.replace("_", " "),
                        "source": fact_root,
                        "kind": "fact",
                    }
                )

    hook_state = _safe_dict(state.get("autoplay_story_hook_state"))
    fired_hooks = _safe_dict(hook_state.get("fired_hooks"))
    for hook_id, payload in fired_hooks.items():
        payload = _safe_dict(payload)
        hook_text = _safe_str(hook_id)
        summary = _safe_str(payload.get("summary"))
        if any(term in hook_text for term in ("lead", "trail", "road", "bridge", "location", "objective_progress")):
            leads.append(
                {
                    "id": hook_text,
                    "name": summary or hook_text.replace("hook:", "").replace("_", " "),
                    "source": "autoplay_story_hook_state",
                    "kind": "hook",
                }
            )

    # If a completed quest left no explicit lead, create a neutral local lead
    # so the campaign can continue instead of ending in active_count == 0.
    if not leads and _completed_quest_count(state) > 0:
        scene = _safe_dict(state.get("scene"))
        label = _safe_str(
            state.get("current_location_name")
            or scene.get("location")
            or scene.get("name")
            or state.get("current_location")
            or "the current area"
        )
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
        label = _norm(_lead_label(lead))
        if not label or label in seen:
            continue
        seen.add(label)
        deduped.append(lead)
    return deduped


def _quest_progress(state: Dict[str, Any]) -> Dict[str, Any]:
    state = _safe_dict(state)
    quest_progress = state.setdefault("quest_progress", {})
    if not isinstance(quest_progress, dict):
        quest_progress = {}
        state["quest_progress"] = quest_progress
    quests = quest_progress.setdefault("quests", {})
    if not isinstance(quests, dict):
        quests = {}
        quest_progress["quests"] = quests
    return quest_progress


def _has_active_quest(state: Dict[str, Any]) -> bool:
    quests = _safe_dict(_quest_progress(state).get("quests"))
    for quest in quests.values():
        quest = _safe_dict(quest)
        if _safe_str(quest.get("status")) == "active" and not quest.get("completed"):
            objectives = [_safe_dict(row) for row in _safe_list(quest.get("objectives"))]
            if not objectives or any(not obj.get("completed") and _safe_str(obj.get("status")) != "completed" for obj in objectives):
                return True
    return False


def _completed_quest_count(state: Dict[str, Any]) -> int:
    quests = _safe_dict(_quest_progress(state).get("quests"))
    count = 0
    for quest in quests.values():
        quest = _safe_dict(quest)
        if quest.get("completed") or _safe_str(quest.get("status")) == "completed":
            count += 1
    return count


def apply_generic_quest_handoff(state: Dict[str, Any]) -> Dict[str, Any]:
    """Activate a generic next objective when a completed quest leaves leads.

    This is intentionally scenario-agnostic. It does not know Bran/Witness/Road.
    It only knows that completed quests can leave unresolved leads.
    """
    state = _safe_dict(state)
    try:
        state = _safe_dict(reconcile_objective_progression_into_quests(state).get("state")) or state
    except Exception:
        pass
    if _has_active_quest(state):
        return {"changed": False, "reason": "active_quest_exists", "state": state}
    if _completed_quest_count(state) <= 0:
        return {"changed": False, "reason": "no_completed_quest", "state": state}

    leads = _iter_unresolved_leads(state)
    if not leads:
        return {"changed": False, "reason": "no_unresolved_leads", "state": state}

    lead = leads[0]
    label = _lead_label(lead)
    quest_id = _stable_id("quest:investigate_lead", label)
    objective_id = _stable_id("objective:investigate_lead", label)

    quest_progress = _quest_progress(state)
    quests = _safe_dict(quest_progress.get("quests"))
    if quest_id in quests:
        return {"changed": False, "reason": "handoff_already_exists", "state": state}

    quests[quest_id] = {
        "quest_id": quest_id,
        "title": f"Investigate Lead: {label}",
        "status": "active",
        "completed": False,
        "source": "generic_quest_handoff",
        "lead": lead,
        "objectives": [
            {
                "objective_id": objective_id,
                "summary": f"Investigate the unresolved lead: {label}.",
                "objective_type": "investigate",
                "subject": label,
                "known_leads": [lead],
                "status": "active",
                "completed": False,
                "completion_rules": [
                    {
                        "semantic_actions": ["inspect", "travel", "ask", "follow"],
                        "topics": [part for part in _norm(label).split() if len(part) > 2],
                    }
                ],
            }
        ],
    }

    handoff_log = state.setdefault("quest_handoff_log", [])
    if isinstance(handoff_log, list):
        handoff_log.append(
            {
                "quest_id": quest_id,
                "objective_id": objective_id,
                "lead": lead,
                "summary": f"Activated generic investigation quest for unresolved lead: {label}.",
            }
        )
        del handoff_log[:-100]

    return {
        "changed": True,
        "reason": "generic_investigate_lead_created",
        "quest_id": quest_id,
        "objective_id": objective_id,
        "lead": lead,
        "state": state,
    }