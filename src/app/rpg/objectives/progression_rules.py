from __future__ import annotations

import re
from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}

def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []

def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _iter_quest_objectives(state: Dict[str, Any]):
    state = _safe_dict(state)
    source_paths = (
        ("quest_progress", "quests"),
        ("quest_log_state", "quests"),
    )
    for root_key, quests_key in source_paths:
        quests = _safe_dict(_safe_dict(state.get(root_key)).get(quests_key))
        for quest_id, quest_raw in quests.items():
            quest = _safe_dict(quest_raw)
            for obj in _safe_list(quest.get("objectives")):
                yield root_key, quest_id, quest, _safe_dict(obj)

    arcs = _safe_dict(_safe_dict(state.get("story_arc_milestone_state")).get("arcs"))
    for arc_id, arc_raw in arcs.items():
        arc = _safe_dict(arc_raw)
        for milestone in _safe_list(arc.get("milestones")):
            milestone = _safe_dict(milestone)
            if "objective_id" not in milestone:
                milestone["objective_id"] = _safe_str(milestone.get("milestone_id") or f"{arc_id}:milestone")
            if "summary" not in milestone:
                milestone["summary"] = _safe_str(milestone.get("title") or milestone.get("objective_text"))
            yield "story_arc_milestone_state", arc_id, arc, milestone


def _norm(value: Any) -> str:
    return " ".join(_safe_str(value).lower().strip().split())

SEMANTIC_ALIASES = {
    "ask": {"ask", "question", "interview", "talk", "speak"},
    "inspect": {"inspect", "search", "examine", "investigate", "look"},
    "travel": {"travel", "go", "leave", "follow", "move"},
    "report": {"report", "tell", "inform", "brief"},
    "recover": {"recover", "retrieve", "collect", "take"},
    "deliver": {"deliver", "bring", "give"},
    "protect": {"protect", "escort", "guard", "warn"},
    "confront": {"confront", "challenge", "accuse", "fight", "stop"},
    "prepare": {"prepare", "buy", "rest", "gather", "equip"},
}

def infer_semantic_action(player_action: str) -> str:
    lower = _norm(player_action)
    for semantic, aliases in SEMANTIC_ALIASES.items():
        if any(lower.startswith(alias + " ") or f" {alias} " in f" {lower} " for alias in aliases):
            return semantic
    if "where" in lower or "who" in lower or "what" in lower or "why" in lower:
        return "ask"
    return "act"

def extract_action_topics(player_action: str) -> List[str]:
    lower = _norm(player_action)
    words = re.findall(r"[a-z][a-z'-]+", lower)
    stop = {
        "i", "the", "a", "an", "to", "from", "with", "about", "for", "of", "and", "or",
        "ask", "inspect", "search", "travel", "follow", "report", "tell", "find", "look",
        "concrete", "specific", "strongest", "known", "lead", "next",
    }
    filtered = [word for word in words if word not in stop and len(word) > 2]
    phrases: List[str] = []
    for i in range(len(filtered) - 1):
        phrases.append(f"{filtered[i]} {filtered[i + 1]}")
    for i in range(len(filtered) - 2):
        phrases.append(f"{filtered[i]} {filtered[i + 1]} {filtered[i + 2]}")
    out: List[str] = []
    for item in filtered + phrases:
        if item not in out:
            out.append(item)
    return out[:40]

def _objective_terms(objective: Dict[str, Any]) -> List[str]:
    text = _norm(" ".join(
        _safe_str(objective.get(key))
        for key in ("objective_id", "title", "summary", "objective_text", "description", "subject", "target")
    ))
    return extract_action_topics(text)

def _matches_terms(action_terms: List[str], objective_terms: List[str]) -> bool:
    if not objective_terms:
        return False
    action_set = set(_norm(term) for term in action_terms if _safe_str(term))
    objective_set = set(_norm(term) for term in objective_terms if _safe_str(term))
    overlap = action_set & objective_set
    if overlap:
        return True
    for action_term in action_set:
        for objective_term in objective_set:
            if len(objective_term) >= 4 and objective_term in action_term:
                return True
            if len(action_term) >= 4 and action_term in objective_term:
                return True
    return False

def _rule_list(objective: Dict[str, Any]) -> List[Dict[str, Any]]:
    rules = _safe_list(_safe_dict(objective).get("completion_rules") or _safe_dict(objective).get("completes_when"))
    return [_safe_dict(rule) for rule in rules if isinstance(rule, dict)]

def _rule_matches(rule: Dict[str, Any], event: Dict[str, Any]) -> bool:
    rule = _safe_dict(rule)
    event = _safe_dict(event)
    semantic = _safe_str(event.get("semantic_action"))
    topics = set(_safe_list(event.get("topics")))
    target = _norm(event.get("target") or event.get("target_name"))
    location = _norm(event.get("location") or event.get("location_name"))

    allowed_semantics = {_safe_str(row) for row in _safe_list(rule.get("semantic_actions")) if _safe_str(row)}
    if allowed_semantics and semantic not in allowed_semantics:
        return False

    required_topics = {_norm(row) for row in _safe_list(rule.get("topics")) if _safe_str(row)}
    if required_topics and not (required_topics & topics):
        return False

    required_targets = {_norm(row) for row in _safe_list(rule.get("targets")) if _safe_str(row)}
    if required_targets and target not in required_targets:
        return False

    required_locations = {_norm(row) for row in _safe_list(rule.get("locations")) if _safe_str(row)}
    if required_locations and location not in required_locations:
        return False

    return True

def build_progression_event(
    *,
    player_action: str,
    semantic_pair: Dict[str, Any] | None = None,
    state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    semantic_pair = _safe_dict(semantic_pair)
    state = _safe_dict(state)
    semantic_action = _safe_str(semantic_pair.get("semantic_action") or semantic_pair.get("activity_label"))
    if not semantic_action or semantic_action == "unknown":
        semantic_action = infer_semantic_action(player_action)
    topics = extract_action_topics(player_action)
    return {
        "player_action": _safe_str(player_action),
        "semantic_action": semantic_action,
        "semantic_family": _safe_str(semantic_pair.get("semantic_family")),
        "target": _safe_str(semantic_pair.get("target") or semantic_pair.get("target_name")),
        "target_name": _safe_str(semantic_pair.get("target_name") or semantic_pair.get("target")),
        "topics": topics,
        "location": _safe_str(state.get("current_location") or state.get("current_location_name") or _safe_dict(state.get("scene")).get("location")),
        "location_name": _safe_str(state.get("current_location_name") or _safe_dict(state.get("scene")).get("location")),
    }

def objective_progress_matches_event(objective: Dict[str, Any], event: Dict[str, Any]) -> bool:
    objective = _safe_dict(objective)
    if bool(objective.get("completed")) or _safe_str(objective.get("status")) == "completed":
        return False

    explicit_rules = _rule_list(objective)
    if explicit_rules:
        return any(_rule_matches(rule, event) for rule in explicit_rules)

    semantic = _safe_str(event.get("semantic_action"))
    action_terms = [_norm(term) for term in _safe_list(event.get("topics"))]
    terms = _objective_terms(objective)
    objective_type = _norm(objective.get("objective_type") or objective.get("type"))

    if objective_type in {"find", "locate", "track", "search"}:
        return semantic in {"ask", "inspect", "travel", "follow"} and _matches_terms(action_terms, terms)
    if objective_type in {"ask", "question", "interview"}:
        return semantic == "ask" and _matches_terms(action_terms, terms)
    if objective_type in {"inspect", "investigate", "search"}:
        return semantic == "inspect" and _matches_terms(action_terms, terms)
    if objective_type in {"report", "inform", "return"}:
        return semantic == "report" and _matches_terms(action_terms, terms)
    if objective_type in {"travel", "follow"}:
        return semantic in {"travel", "follow"} and _matches_terms(action_terms, terms)
    if objective_type in {"recover", "retrieve"}:
        return semantic in {"recover", "inspect"} and _matches_terms(action_terms, terms)
    if objective_type in {"deliver"}:
        return semantic == "deliver" and _matches_terms(action_terms, terms)
    if objective_type in {"protect", "escort", "warn"}:
        return semantic in {"protect", "ask", "travel"} and _matches_terms(action_terms, terms)
    if objective_type in {"confront"}:
        return semantic in {"confront", "ask"} and _matches_terms(action_terms, terms)
    if objective_type in {"prepare"}:
        return semantic in {"prepare", "ask"} and _matches_terms(action_terms, terms)

    return _matches_terms(action_terms, terms) and semantic in {
        "ask", "inspect", "travel", "follow", "report", "recover", "deliver", "protect", "confront", "prepare"
    }


def objective_partial_progress_matches_event(objective: Dict[str, Any], event: Dict[str, Any]) -> bool:
    if bool(_safe_dict(objective).get("completed")) or _safe_str(_safe_dict(objective).get("status")) == "completed":
        return False
    semantic = _safe_str(_safe_dict(event).get("semantic_action"))
    if semantic not in {"ask", "inspect", "travel", "follow", "report", "recover", "deliver", "protect", "confront", "prepare"}:
        return False
    action_terms = [_norm(term) for term in _safe_list(_safe_dict(event).get("topics"))]
    terms = _objective_terms(_safe_dict(objective))
    return _matches_terms(action_terms, terms)


def apply_objective_progression_rules(
    state: Dict[str, Any],
    *,
    player_action: str,
    semantic_pair: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    state = _safe_dict(state)
    event = build_progression_event(player_action=player_action, semantic_pair=semantic_pair, state=state)
    completed: List[Dict[str, Any]] = []
    progressed: List[Dict[str, Any]] = []
    touched_quests: List[Dict[str, Any]] = []
    for source_key, quest_id, quest, obj in _iter_quest_objectives(state):
        if objective_progress_matches_event(obj, event):
            obj["completed"] = True
            obj["status"] = "completed"
            completed.append({
                "source": source_key,
                "quest_id": _safe_str(quest.get("quest_id") or quest_id),
                "objective_id": _safe_str(obj.get("objective_id") or obj.get("id")),
                "summary": _safe_str(obj.get("summary") or obj.get("objective_text") or obj.get("title")),
                "event": event,
                "matched": True,
                "completed": True,
                "partial": False,
            })
            if quest not in touched_quests:
                touched_quests.append(quest)
        elif objective_partial_progress_matches_event(obj, event):
            progress_count = int(obj.get("progress_count", 0)) + 1
            obj["progress_count"] = progress_count
            obj["status"] = _safe_str(obj.get("status") or "active")
            progressed.append({
                "source": source_key,
                "quest_id": _safe_str(quest.get("quest_id") or quest_id),
                "objective_id": _safe_str(obj.get("objective_id") or obj.get("id")),
                "summary": _safe_str(obj.get("summary") or obj.get("objective_text") or obj.get("title")),
                "progress_count": progress_count,
                "event": event,
                "matched": True,
                "completed": False,
                "partial": True,
            })
            if quest not in touched_quests:
                touched_quests.append(quest)

    for quest in touched_quests:
        objectives = _safe_list(quest.get("objectives") or quest.get("milestones"))
        if objectives and all(
            bool(_safe_dict(obj).get("completed")) or _safe_str(_safe_dict(obj).get("status")) == "completed"
            for obj in objectives
        ):
            quest["completed"] = True
            quest["status"] = "completed"

    progress_log = state.setdefault("objective_progression_log", [])
    if isinstance(progress_log, list):
        # Calculate metrics
        evaluated_count = 0
        matched_count = 0
        completed_count = 0
        partial_count = 0
        unmatched_count = 0
        if completed:
            completed_count = len(completed)
        if progressed:
            partial_count = len(progressed)
        evaluated_count = completed_count + partial_count
        matched_count = completed_count + partial_count
        unmatched_count = 1 if not completed and not progressed else 0
        ok = matched_count > 0

        if not completed and not progressed:
            progress_log.append({
                "partial": False,
                "matched": False,
                "completed": False,
                "event": event,
                "summary": "Objective progression evaluated but no objective matched.",
                "evaluated_count": evaluated_count,
                "matched_count": matched_count,
                "completed_count": completed_count,
                "partial_count": partial_count,
                "unmatched_count": unmatched_count,
                "ok": ok,
            })
        for row in completed:
            row = dict(row)
            row["matched"] = True
            row["completed"] = True
            row["evaluated_count"] = evaluated_count
            row["matched_count"] = matched_count
            row["completed_count"] = completed_count
            row["partial_count"] = partial_count
            row["unmatched_count"] = unmatched_count
            row["ok"] = ok
            progress_log.append(row)
        for row in progressed:
            row = dict(row)
            row.setdefault("partial", True)
            row.setdefault("matched", True)
            row.setdefault("completed", False)
            row["evaluated_count"] = evaluated_count
            row["matched_count"] = matched_count
            row["completed_count"] = completed_count
            row["partial_count"] = partial_count
            row["unmatched_count"] = unmatched_count
            row["ok"] = ok
            progress_log.append(row)
        del progress_log[:-100]

    return {
        "changed": bool(completed or progressed),
        "completed_objectives": completed,
        "progressed_objectives": progressed,
        "event": event,
        "simulation_state": state,
    }
