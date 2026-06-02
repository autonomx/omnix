from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.quests.givers import available_quest_offers, register_quest_offer
from app.rpg.quests.rumors import propagate_backed_rumors
from app.rpg.quests.state import normalize_quest_state
from app.rpg.quests.templates import list_quest_templates

SOURCE = "deterministic_work_inquiry_runtime"

WORK_INTENT_TERMS = {
    "work",
    "job",
    "jobs",
    "quest",
    "quests",
    "help",
    "rumor",
    "rumors",
    "lead",
    "leads",
    "task",
    "tasks",
}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _tokenize(text: str) -> set[str]:
    stripped = [chunk.strip(".,!?;:'\"()[]{}") for chunk in _safe_str(text).lower().split()]
    return {chunk for chunk in stripped if chunk}


def classify_work_inquiry(player_text: str) -> Dict[str, Any]:
    tokens = _tokenize(player_text)
    matched_terms = sorted(tokens.intersection(WORK_INTENT_TERMS))
    return {
        "ok": bool(matched_terms),
        "reason": "work_inquiry_detected" if matched_terms else "work_inquiry_not_detected",
        "matched_terms": matched_terms,
        "source": SOURCE,
    }


def route_work_inquiry(
    simulation_state: Dict[str, Any],
    *,
    giver_id: str,
    player_text: str,
    turn_index: int = 0,
) -> Dict[str, Any]:
    classification = classify_work_inquiry(player_text)
    if not classification.get("ok"):
        return {"ok": False, "reason": "not_work_inquiry", "classification": classification, "source": SOURCE}

    registered = []
    for quest_id, template in list_quest_templates().items():
        if _safe_str(template.get("giver_id")) != giver_id:
            continue
        result = register_quest_offer(simulation_state, giver_id=giver_id, quest_id=quest_id, turn_index=turn_index)
        registered.append(result)
    offers = available_quest_offers(simulation_state, giver_id=giver_id)
    backed_rumors = propagate_backed_rumors(simulation_state)
    suggestions = suggest_objectives(simulation_state, limit=3)
    return {
        "ok": True,
        "reason": "work_inquiry_routed",
        "giver_id": giver_id,
        "classification": classification,
        "registered_offers": deepcopy(registered),
        "offers": offers,
        "backed_rumors": backed_rumors,
        "objective_suggestions": suggestions,
        "source": SOURCE,
    }


def suggest_objectives(simulation_state: Dict[str, Any], *, limit: int = 3) -> Dict[str, Any]:
    quest_state = normalize_quest_state(_safe_dict(simulation_state).get("quest_state"))
    suggestions = []
    for quest_id, quest in sorted(_safe_dict(quest_state.get("quests")).items()):
        if quest.get("status") != "active":
            continue
        for objective_id, objective in sorted(_safe_dict(quest.get("objectives")).items()):
            if objective.get("status") != "open":
                continue
            suggestions.append(
                {
                    "quest_id": quest_id,
                    "objective_id": objective_id,
                    "quest_title": quest.get("title"),
                    "description": objective.get("description") or objective_id,
                    "suggested_action": _suggest_action_for_objective(objective),
                    "source": SOURCE,
                }
            )
            if len(suggestions) >= max(1, int(limit or 1)):
                return {"ok": True, "reason": "objective_suggestions_built", "suggestions": suggestions, "source": SOURCE}
    return {"ok": True, "reason": "objective_suggestions_built", "suggestions": suggestions, "source": SOURCE}


def build_work_inquiry_narration_contract(route_result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(route_result)
    allowed_claims = []
    for offer in _safe_list(_safe_dict(result.get("offers")).get("offers")):
        if not isinstance(offer, dict):
            continue
        allowed_claims.append(f"Quest offer available: {_safe_str(offer.get('quest_id'))}")
    for suggestion in _safe_list(_safe_dict(result.get("objective_suggestions")).get("suggestions")):
        if not isinstance(suggestion, dict):
            continue
        allowed_claims.append(f"Objective suggestion: {_safe_str(suggestion.get('quest_id'))} / {_safe_str(suggestion.get('objective_id'))}")
    return {
        "source": SOURCE,
        "allowed_work_claims": allowed_claims,
        "forbidden_work_claims": [
            "Do not invent unavailable jobs or quest rewards.",
            "Do not mark objectives complete from a work inquiry.",
            "Do not claim a quest was accepted unless the deterministic quest giver state says accepted.",
        ],
    }


def _suggest_action_for_objective(objective: Dict[str, Any]) -> str:
    metadata = _safe_dict(objective.get("metadata"))
    objective_type = _safe_str(metadata.get("type"))
    target_ids = [_safe_str(row) for row in _safe_list(metadata.get("target_ids")) if _safe_str(row)]
    if objective_type == "defeat" and target_ids:
        return f"Track and defeat {target_ids[0]}."
    if objective_type == "collect" and target_ids:
        return f"Find and collect {target_ids[0]}."
    if objective_type == "talk" and target_ids:
        return f"Speak with {target_ids[0]}."
    return _safe_str(objective.get("description")) or "Review the current objective."
