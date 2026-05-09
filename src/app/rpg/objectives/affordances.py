from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from app.rpg.objectives.reconciliation import reconcile_objective_progression_into_quests


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}

def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []

def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""

def _norm(value: Any) -> str:
    return " ".join(_safe_str(value).lower().strip().split())

OBJECTIVE_VERB_ALIASES = {
    "find": {"find", "locate", "track", "search for", "discover"},
    "ask": {"ask", "question", "interview", "speak to", "talk to"},
    "inspect": {"inspect", "examine", "search", "investigate", "look for"},
    "report": {"report", "tell", "inform", "return to", "brief"},
    "travel": {"travel", "go to", "leave for", "follow", "head to", "move to"},
    "recover": {"recover", "retrieve", "take back", "collect", "obtain"},
    "deliver": {"deliver", "bring", "give", "carry"},
    "protect": {"protect", "escort", "guard", "warn"},
    "confront": {"confront", "challenge", "accuse", "stop"},
    "prepare": {"prepare", "rest", "buy", "gather", "equip"},
}

ACTION_TEMPLATES = {
    "ask": "I ask {target} what they personally know about {subject}, where it was last seen, and who or what I should inspect next.",
    "ask_witness": "I ask {target} who last saw {subject}, where they saw it, and what physical clue points to the next place.",
    "inspect": "I inspect {target} for signs of {subject}: tracks, marks, damage, residue, missing items, witnesses, or hidden clues.",
    "travel": "I travel to {target} and immediately search the area for signs connected to {subject}.",
    "follow": "I follow the strongest lead toward {target}, watching for tracks, witnesses, marks, hazards, or evidence of {subject}.",
    "report": "I report the evidence about {subject} to {target}, explain what I found, and ask what objective this unlocks next.",
    "recover": "I search {target} for {subject}, check for traps or witnesses, and secure it if it is present.",
    "deliver": "I deliver {subject} to {target}, confirm receipt, and ask whether anything changed because of it.",
    "protect": "I warn {target} about the danger connected to {subject} and take a practical step to protect them.",
    "confront": "I confront {target} about {subject}, citing the strongest evidence I have.",
    "prepare": "I prepare for {subject} by checking supplies, equipment, allies, route risks, and known hazards.",
}

GENERIC_STOPWORDS = {
    "the", "a", "an", "to", "from", "with", "about", "for", "of", "and", "or",
    "current", "objective", "quest", "lead", "next", "thing", "something",
}


PLANNER_LANGUAGE_PATTERNS = (
    "specific question",
    "concrete lead",
    "strongest lead",
    "act on next",
    "current objective",
    "make progress",
    "next concrete",
)


def command_has_planner_language(command: str) -> bool:
    lower = _norm(command)
    return any(pattern in lower for pattern in PLANNER_LANGUAGE_PATTERNS)

def objective_blob(objective: Dict[str, Any]) -> str:
    objective = _safe_dict(objective)
    fields = [
        objective.get("objective_id"),
        objective.get("title"),
        objective.get("summary"),
        objective.get("objective_text"),
        objective.get("description"),
        objective.get("type"),
        objective.get("objective_type"),
    ]
    return " ".join(_safe_str(value) for value in fields if _safe_str(value))

def infer_objective_type(objective: Dict[str, Any]) -> str:
    explicit = _norm(_safe_dict(objective).get("objective_type") or _safe_dict(objective).get("type"))
    if explicit:
        return explicit
    text = _norm(objective_blob(objective))
    for objective_type, aliases in OBJECTIVE_VERB_ALIASES.items():
        if any(alias in text for alias in aliases):
            return objective_type
    if any(term in text for term in ("where", "who knows", "information", "witness", "rumor")):
        return "ask"
    if any(term in text for term in ("track", "trail", "clue", "sign", "mark")):
        return "inspect"
    return "advance"

def _entity_candidates_from_objective(objective: Dict[str, Any]) -> List[str]:
    objective = _safe_dict(objective)
    entities: List[str] = []
    for key in ("subject", "target", "npc", "npc_id", "location", "location_id", "item", "item_id", "quest_giver"):
        value = _safe_str(objective.get(key)).strip()
        if value and value not in entities:
            entities.append(value)
    for row in _safe_list(objective.get("known_leads")):
        if isinstance(row, dict):
            value = _safe_str(row.get("name") or row.get("title") or row.get("id")).strip()
        else:
            value = _safe_str(row).strip()
        if value and value not in entities:
            entities.append(value)
    return entities

def infer_subject(objective: Dict[str, Any]) -> str:
    objective = _safe_dict(objective)
    explicit = _safe_str(objective.get("subject") or objective.get("item") or objective.get("target_subject")).strip()
    if explicit:
        return explicit
    text = _safe_str(objective.get("objective_text") or objective.get("summary") or objective.get("title") or "").strip()
    cleaned = re.sub(
        r"^(find|locate|track|recover|retrieve|ask|question|inspect|search|investigate|report|deliver|protect|escort|warn|confront|prepare)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip(" .")
    # Keep useful direct objects, but remove generic trailing instructions.
    cleaned = re.sub(r"\b(and|then)\b.*$", "", cleaned, flags=re.IGNORECASE).strip(" .")
    cleaned = re.sub(r"\b(to|with|about|for)\s+(the\s+)?(current|next|strongest|concrete)\b.*$", "", cleaned, flags=re.IGNORECASE).strip(" .")
    if cleaned:
        return cleaned
    tokens = [tok for tok in re.findall(r"[A-Za-z][A-Za-z'-]+", text) if tok.lower() not in GENERIC_STOPWORDS]
    return " ".join(tokens[:4]) if tokens else "the objective"

def infer_best_target(objective: Dict[str, Any], state: Dict[str, Any], *, prefer_quest_giver: bool = False) -> str:
    objective = _safe_dict(objective)
    state = _safe_dict(state)
    if prefer_quest_giver:
        quest_giver = _safe_str(objective.get("quest_giver") or objective.get("source_npc") or objective.get("giver")).strip()
        if quest_giver:
            return quest_giver
    # If known_leads exist, prefer them as targets for inspect/recover actions
    known_leads = _safe_list(objective.get("known_leads"))
    if known_leads:
        # Use the first known_lead as the target
        lead = known_leads[0]
        if isinstance(lead, dict):
            lead_val = _safe_str(lead.get("name") or lead.get("title") or lead.get("id")).strip()
        else:
            lead_val = _safe_str(lead).strip()
        if lead_val:
            return lead_val
    candidates = _entity_candidates_from_objective(objective)
    if candidates:
        return candidates[0]
    for key in ("nearby_npcs", "present_npcs"):
        for row in _safe_list(state.get(key) or _safe_dict(state.get("scene")).get(key)):
            row = _safe_dict(row)
            name = _safe_str(row.get("name") or row.get("npc_id")).strip()
            if name:
                return name
    location = _safe_str(state.get("current_location_name") or state.get("current_location") or _safe_dict(state.get("scene")).get("location")).strip()
    if location:
        return location
    return "the strongest known lead"


def infer_best_clue_or_location_target(objective: Dict[str, Any], state: Dict[str, Any]) -> str:
    objective = _safe_dict(objective)
    leads = _safe_list(objective.get("known_leads"))
    for row in leads:
        if isinstance(row, dict):
            lead_type = _norm(row.get("type") or row.get("kind") or row.get("category"))
            name = _safe_str(row.get("name") or row.get("title") or row.get("id")).strip()
            if name and lead_type in {"location", "place", "clue", "trail", "item", "object"}:
                return name
        else:
            name = _safe_str(row).strip()
            if name:
                return name
    for key in ("location", "location_id", "clue", "clue_location", "target_location"):
        value = _safe_str(objective.get(key)).strip()
        if value:
            return value
    return infer_best_target(objective, state)

def objective_is_completed(objective: Dict[str, Any]) -> bool:
    objective = _safe_dict(objective)
    return bool(objective.get("completed")) or _safe_str(objective.get("status")) == "completed"

def objective_affordance_actions(
    objective: Dict[str, Any],
    state: Dict[str, Any],
    *,
    index: int = 0,
) -> List[Dict[str, Any]]:
    objective = _safe_dict(objective)
    if objective_is_completed(objective):
        return []

    objective_type = infer_objective_type(objective)
    subject = infer_subject(objective)
    target = infer_best_target(objective, state)
    clue_target = infer_best_clue_or_location_target(objective, state)
    quest_giver = infer_best_target(objective, state, prefer_quest_giver=True)
    objective_id = _safe_str(objective.get("objective_id") or objective.get("id") or f"objective:{index}")

    action_specs: List[Tuple[str, str, str, str, int]] = []
    if objective_type in {"find", "locate", "track", "search"}:
        action_specs.extend([
            ("ask", "Ask who last saw it", ACTION_TEMPLATES["ask_witness"].format(target=quest_giver, subject=subject), "objective", 140),
            ("inspect", "Inspect the best clue site", ACTION_TEMPLATES["inspect"].format(target=clue_target, subject=subject), "exploration", 138),
            ("follow", "Follow the best lead", ACTION_TEMPLATES["follow"].format(target=clue_target, subject=subject), "travel", 134),
        ])
    elif objective_type in {"ask", "question", "interview"}:
        action_specs.append(("ask", "Ask a specific question", ACTION_TEMPLATES["ask"].format(target=target, subject=subject), "social", 138))
    elif objective_type in {"inspect", "investigate", "search"}:
        action_specs.append(("inspect", "Inspect for evidence", ACTION_TEMPLATES["inspect"].format(target=target, subject=subject), "exploration", 138))
    elif objective_type in {"report", "inform", "return"}:
        action_specs.append(("report", "Report findings", ACTION_TEMPLATES["report"].format(target=quest_giver, subject=subject), "objective", 142))
    elif objective_type in {"travel", "follow"}:
        action_specs.append(("travel", "Travel to lead", ACTION_TEMPLATES["travel"].format(target=target, subject=subject), "travel", 138))
    elif objective_type in {"recover", "retrieve"}:
        action_specs.extend([
            ("inspect", "Search recovery site", ACTION_TEMPLATES["inspect"].format(target=target, subject=subject), "exploration", 136),
            ("recover", "Recover item", ACTION_TEMPLATES["recover"].format(target=target, subject=subject), "objective", 140),
        ])
    elif objective_type in {"deliver"}:
        action_specs.append(("deliver", "Deliver objective item", ACTION_TEMPLATES["deliver"].format(target=target, subject=subject), "objective", 140))
    elif objective_type in {"protect", "escort", "warn"}:
        action_specs.append(("protect", "Protect or warn target", ACTION_TEMPLATES["protect"].format(target=target, subject=subject), "objective", 140))
    elif objective_type in {"confront"}:
        action_specs.append(("confront", "Confront target", ACTION_TEMPLATES["confront"].format(target=target, subject=subject), "social", 136))
    elif objective_type in {"prepare"}:
        action_specs.append(("prepare", "Prepare for objective", ACTION_TEMPLATES["prepare"].format(subject=subject), "service", 130))
    else:
        action_specs.extend([
            ("ask", "Ask for actionable facts", ACTION_TEMPLATES["ask"].format(target=quest_giver, subject=subject), "objective", 120),
            ("inspect", "Inspect the best target", ACTION_TEMPLATES["inspect"].format(target=clue_target, subject=subject), "exploration", 118),
            ("travel", "Travel to the best target", ACTION_TEMPLATES["travel"].format(target=clue_target, subject=subject), "travel", 116),
        ])

    out: List[Dict[str, Any]] = []
    seen_commands = set()
    for local_index, (kind, label, command, category, priority) in enumerate(action_specs):
        command = " ".join(command.split())
        if command_has_planner_language(command):
            command = command.replace("what concrete lead I should act on next", "which place, person, or clue I should inspect next")
            command = command.replace("the strongest lead", target)
            command = command.replace("concrete signs", "physical signs")
        if command in seen_commands:
            continue
        seen_commands.add(command)
        out.append({
            "action_id": f"affordance:{objective_id}:{kind}:{local_index}",
            "label": label,
            "command": command,
            "category": category,
            "priority": int(priority) - int(index or 0),
            "objective_id": objective_id,
            "objective_type": objective_type,
            "subject": subject,
            "target": target,
            "reason": "Generated by scenario-agnostic objective affordance engine.",
            "metadata": {
                "affordance_kind": kind,
                "objective_type": objective_type,
                "subject": subject,
                "target": target,
                "scenario_agnostic": True,
            },
        })
    return out

def collect_active_objectives(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    state = _safe_dict(state)
    try:
        state = _safe_dict(reconcile_objective_progression_into_quests(state).get("state")) or state
    except Exception:
        pass
    out: List[Dict[str, Any]] = []

    quest_sources = [
        _safe_dict(_safe_dict(state.get("quest_progress")).get("quests")),
        _safe_dict(_safe_dict(state.get("quest_log_state")).get("quests")),
    ]
    for quests in quest_sources:
        for quest_id, quest in quests.items():
            quest = _safe_dict(quest)
            if _safe_str(quest.get("status")) == "completed" or quest.get("completed"):
                continue
            for obj in _safe_list(quest.get("objectives")):
                obj = dict(_safe_dict(obj))
                if objective_is_completed(obj):
                    continue
                obj.setdefault("quest_id", _safe_str(quest.get("quest_id") or quest_id))
                obj.setdefault("quest_title", _safe_str(quest.get("title") or quest_id))
                obj.setdefault("quest_giver", _safe_str(quest.get("quest_giver") or quest.get("source_npc") or quest.get("giver")))
                obj.setdefault("quest_source", _safe_str(quest.get("source")))
                obj.setdefault("quest_priority", int(quest.get("priority") or 0))
                obj.setdefault("handoff_quest", bool(quest.get("handoff_quest")))
                obj.setdefault("handoff_objective", bool(obj.get("handoff_objective")))
                obj.setdefault(
                    "affordance_priority",
                    int(obj.get("affordance_priority") or quest.get("priority") or 0),
                )
                out.append(obj)

    arcs = _safe_dict(_safe_dict(state.get("story_arc_milestone_state")).get("arcs"))
    for arc_id, arc in arcs.items():
        arc = _safe_dict(arc)
        for milestone in _safe_list(arc.get("milestones")):
            milestone = dict(_safe_dict(milestone))
            if _safe_str(milestone.get("status")) == "completed" or milestone.get("completed"):
                continue
            milestone.setdefault("objective_id", _safe_str(milestone.get("milestone_id") or f"{arc_id}:milestone"))
            milestone.setdefault("summary", _safe_str(milestone.get("objective_text") or milestone.get("title")))
            milestone.setdefault("quest_id", _safe_str(arc_id))
            milestone.setdefault("quest_title", _safe_str(arc.get("title") or arc_id))
            out.append(milestone)

    # De-dupe by objective_id/summary.
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for obj in out:
        key = _safe_str(obj.get("objective_id")) or _norm(obj.get("summary") or obj.get("objective_text") or obj.get("title"))
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        deduped.append(obj)
    deduped.sort(
        key=lambda row: (
            -int(_safe_dict(row).get("affordance_priority") or 0),
            0 if _safe_dict(row).get("handoff_objective") else 1,
            _safe_str(_safe_dict(row).get("quest_id")),
            _safe_str(_safe_dict(row).get("objective_id")),
        )
    )
    return deduped

def build_objective_affordances_for_state(state: Dict[str, Any], *, limit: int = 12) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    for index, objective in enumerate(collect_active_objectives(state)):
        objective = _safe_dict(objective)
        if objective.get("handoff_objective"):
            for action in _safe_list(objective.get("suggested_actions")):
                command = _safe_str(action).strip()
                if command:
                    actions.append(
                        {
                            "command": command,
                            "source": "handoff_objective_suggested_action",
                            "objective_id": _safe_str(objective.get("objective_id")),
                            "quest_id": _safe_str(objective.get("quest_id")),
                            "semantic": "investigate",
                            "priority": int(objective.get("affordance_priority") or 100),
                        }
                    )
        actions.extend(objective_affordance_actions(objective, state, index=index))
    actions.sort(
        key=lambda row: (
            -int(_safe_dict(row).get("priority") or 0),
            _safe_str(_safe_dict(row).get("source")),
            _safe_str(_safe_dict(row).get("command")),
        )
    )
    return actions[: max(1, int(limit or 12))]
