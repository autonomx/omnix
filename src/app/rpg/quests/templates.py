from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

SOURCE = "deterministic_quest_templates"

DEFAULT_QUEST_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "quest:clear_the_road": {
        "quest_id": "quest:clear_the_road",
        "title": "Clear the Road",
        "summary": "Help Bran make the old mill road safe again.",
        "giver_id": "npc:bran",
        "start_stage": "offered",
        "tags": ["rusty_flagon", "bandits", "starter"],
        "prerequisites": [{"type": "always"}],
        "objectives": [
            {
                "objective_id": "objective:defeat_bandit",
                "description": "Defeat the bandit threatening the old mill road.",
                "type": "defeat",
                "target_ids": ["enemy:bandit_1"],
                "required": 1,
            }
        ],
        "rewards": [
            {"type": "currency", "currency": {"silver": 12}},
            {"type": "relationship", "npc_id": "npc:bran", "trust": 5},
        ],
    }
}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _normalize_objective(value: Dict[str, Any]) -> Dict[str, Any]:
    value = _safe_dict(value)
    objective_id = _safe_str(value.get("objective_id"))
    return {
        "objective_id": objective_id,
        "description": _safe_str(value.get("description")) or objective_id,
        "type": _safe_str(value.get("type")) or "generic",
        "target_ids": [_safe_str(row) for row in _safe_list(value.get("target_ids")) if _safe_str(row)],
        "required": max(1, int(value.get("required") or 1)),
        "metadata": dict(_safe_dict(value.get("metadata"))),
        "source": SOURCE,
    }


def normalize_quest_template(value: Dict[str, Any], *, quest_id: str = "") -> Dict[str, Any]:
    value = _safe_dict(value)
    normalized_id = _safe_str(value.get("quest_id")) or quest_id
    objectives = [
        _normalize_objective(row)
        for row in _safe_list(value.get("objectives"))
        if _safe_dict(row).get("objective_id")
    ]
    return {
        "quest_id": normalized_id,
        "title": _safe_str(value.get("title")) or normalized_id,
        "summary": _safe_str(value.get("summary")),
        "giver_id": _safe_str(value.get("giver_id")),
        "start_stage": _safe_str(value.get("start_stage")) or "offered",
        "tags": [_safe_str(row) for row in _safe_list(value.get("tags")) if _safe_str(row)],
        "prerequisites": [dict(row) for row in _safe_list(value.get("prerequisites")) if isinstance(row, dict)],
        "objectives": objectives,
        "rewards": [dict(row) for row in _safe_list(value.get("rewards")) if isinstance(row, dict)],
        "source": SOURCE,
    }


def list_quest_templates(registry: Dict[str, Dict[str, Any]] | None = None) -> Dict[str, Dict[str, Any]]:
    registry = registry or DEFAULT_QUEST_TEMPLATES
    return {
        quest_id: normalize_quest_template(template, quest_id=quest_id)
        for quest_id, template in sorted(registry.items())
    }


def get_quest_template(quest_id: str, registry: Dict[str, Dict[str, Any]] | None = None) -> Dict[str, Any]:
    registry = registry or DEFAULT_QUEST_TEMPLATES
    template = _safe_dict(registry.get(_safe_str(quest_id)))
    if not template:
        return {}
    return normalize_quest_template(template, quest_id=_safe_str(quest_id))


def quest_template_to_start_payload(template: Dict[str, Any]) -> Dict[str, Any]:
    template = normalize_quest_template(template)
    objectives = {
        row["objective_id"]: {
            "objective_id": row["objective_id"],
            "description": row["description"],
            "status": "open",
            "metadata": {
                "type": row["type"],
                "target_ids": list(row["target_ids"]),
                "required": row["required"],
            },
        }
        for row in template["objectives"]
    }
    return {
        "quest_id": template["quest_id"],
        "title": template["title"],
        "stage": template["start_stage"],
        "objectives": objectives,
        "rewards": deepcopy(template["rewards"]),
        "metadata": {"summary": template["summary"], "giver_id": template["giver_id"], "tags": list(template["tags"])},
        "source": SOURCE,
    }
