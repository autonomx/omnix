from __future__ import annotations

import json
from typing import Any, Dict, List

_ALLOWED_ACTION_TYPES = {
    "attack_melee",
    "attack_ranged",
    "attack_unarmed",
    "block",
    "dodge",
    "parry",
    "persuade",
    "intimidate",
    "deceive",
    "sneak",
    "investigate",
    "hack",
    "cast_spell",
    "use_item",
    "pickup_item",
    "drop_item",
    "equip_item",
    "unequip_item",
    "observe",
    "social_activity",
    "social_competition",
    "social_affection",
    "social_performance",
    "trade",
    "ritual",
    "exploration",
    "threat",
}

_ALLOWED_DIFFICULTIES = {"trivial", "easy", "normal", "hard", "extreme"}
_ALLOWED_SKILLS = {
    "swordsmanship",
    "archery",
    "firearms",
    "defense",
    "stealth",
    "persuasion",
    "intimidation",
    "investigation",
    "magic",
    "hacking",
    "performance",
    "barter",
    "ritual",
}


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
    if isinstance(v, list):
        return v
    return []


def _safe_str(v: Any) -> str:
    return str(v) if v is not None else ""


def _clip_text(text: Any, limit: int = 240) -> str:
    value = _safe_str(text).strip()
    return value[:limit]


def build_action_intelligence_prompt(
    player_input: str,
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    candidate_action: Dict[str, Any],
) -> str:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)
    candidate_action = _safe_dict(candidate_action)
    player_state = _safe_dict(simulation_state.get("player_state"))
    current_scene = _safe_dict(runtime_state.get("current_scene") or simulation_state.get("current_scene"))
    npcs = _safe_dict(simulation_state.get("npcs"))

    present_ids = _safe_list(current_scene.get("present_npc_ids"))
    nearby_npcs = []
    for npc_id in present_ids[:6]:
        npc = _safe_dict(npcs.get(npc_id))
        if npc:
            nearby_npcs.append({
                "npc_id": _safe_str(npc.get("npc_id") or npc_id),
                "name": _clip_text(npc.get("name"), 60),
                "role": _clip_text(npc.get("role"), 60),
                "faction": _clip_text(npc.get("faction"), 60),
            })

    payload = {
        "player_input": _clip_text(player_input, 240),
        "candidate_action": {
            "action_type": _safe_str(candidate_action.get("action_type")),
            "target_id": _safe_str(candidate_action.get("target_id")),
            "npc_id": _safe_str(candidate_action.get("npc_id")),
            "item_id": _safe_str(candidate_action.get("item_id")),
        },
        "scene": {
            "scene_id": _safe_str(current_scene.get("scene_id")),
            "location_id": _safe_str(current_scene.get("location_id")),
            "title": _clip_text(current_scene.get("title"), 80),
            "summary": _clip_text(current_scene.get("summary"), 160),
        },
        "player": {
            "level": int(player_state.get("level", 1) or 1),
            "stats": _safe_dict(player_state.get("stats")),
            "skills": {
                key: {
                    "level": int(_safe_dict(value).get("level", 0) or 0)
                }
                for key, value in sorted(_safe_dict(player_state.get("skills")).items())
            },
        },
        "nearby_npcs": nearby_npcs,
        "allowed_action_types": sorted(_ALLOWED_ACTION_TYPES),
        "allowed_difficulties": sorted(_ALLOWED_DIFFICULTIES),
        "allowed_skills": sorted(_ALLOWED_SKILLS),
    }

    instructions = (
        "You are an RPG action analysis assistant.\n"
        "Return JSON only.\n"
        "Do not decide outcomes, damage, XP, hit chance, or success.\n"
        "You may only suggest bounded action metadata.\n"
        "Schema:\n"
        "{\n"
        '  "action_type": string,\n'
        '  "difficulty": string,\n'
        '  "skill_id": string,\n'
        '  "intent_tags": [string],\n'
        '  "narrative_goal": string,\n'
        '  "target_id": string,\n'
        '  "target_name": string,\n'
        '  "reason": string\n'
        "}\n"
        "Prefer the candidate_action action_type unless the text clearly implies a better allowed action.\n"
    )
    return instructions + "\nINPUT:\n" + json.dumps(payload, sort_keys=True)


def _extract_json_object(text: str) -> Dict[str, Any]:
    text = _safe_str(text).strip()
    if not text:
        return {}
    try:
        return _safe_dict(json.loads(text))
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return _safe_dict(json.loads(text[start:end + 1]))
        except Exception:
            return {}
    return {}


def normalize_action_advisory(advisory: Dict[str, Any], candidate_action: Dict[str, Any]) -> Dict[str, Any]:
    advisory = _safe_dict(advisory)
    candidate_action = _safe_dict(candidate_action)

    action_type = _safe_str(advisory.get("action_type")).strip().lower()
    if action_type not in _ALLOWED_ACTION_TYPES:
        action_type = _safe_str(candidate_action.get("action_type")).strip().lower()
    if action_type not in _ALLOWED_ACTION_TYPES:
        action_type = "investigate"

    difficulty = _safe_str(advisory.get("difficulty")).strip().lower()
    if difficulty not in _ALLOWED_DIFFICULTIES:
        difficulty = _safe_str(candidate_action.get("difficulty")).strip().lower()
    if difficulty not in _ALLOWED_DIFFICULTIES:
        difficulty = "normal"

    skill_id = _safe_str(advisory.get("skill_id")).strip().lower()
    if skill_id not in _ALLOWED_SKILLS:
        skill_id = _safe_str(candidate_action.get("skill_id")).strip().lower()
    if skill_id not in _ALLOWED_SKILLS:
        skill_id = ""

    intent_tags = []
    for value in _safe_list(advisory.get("intent_tags"))[:6]:
        tag = _safe_str(value).strip().lower().replace(" ", "_")
        if tag:
            intent_tags.append(tag[:32])

    return {
        "action_type": action_type,
        "difficulty": difficulty,
        "skill_id": skill_id,
        "intent_tags": intent_tags,
        "narrative_goal": _clip_text(advisory.get("narrative_goal"), 120),
        "target_id": _safe_str(advisory.get("target_id") or candidate_action.get("target_id") or candidate_action.get("npc_id")).strip(),
        "target_name": _clip_text(advisory.get("target_name"), 80),
        "reason": _clip_text(advisory.get("reason"), 160),
    }


def merge_action_advisory(candidate_action: Dict[str, Any], advisory: Dict[str, Any]) -> Dict[str, Any]:
    candidate_action = _safe_dict(candidate_action)
    advisory = _safe_dict(advisory)
    merged = dict(candidate_action)

    merged["action_type"] = _safe_str(advisory.get("action_type") or candidate_action.get("action_type")).strip()
    if advisory.get("difficulty"):
        merged["difficulty"] = advisory.get("difficulty")
    if advisory.get("skill_id"):
        merged["skill_id"] = advisory.get("skill_id")
    if advisory.get("target_id"):
        merged["target_id"] = advisory.get("target_id")
    if advisory.get("target_name"):
        merged["target_name"] = advisory.get("target_name")

    metadata = _safe_dict(merged.get("metadata"))
    metadata["intent_tags"] = _safe_list(advisory.get("intent_tags"))
    metadata["narrative_goal"] = _safe_str(advisory.get("narrative_goal"))
    metadata["llm_reason"] = _safe_str(advisory.get("reason"))
    metadata["llm_advisory"] = True
    merged["metadata"] = metadata
    return merged


def get_action_advisory(
    llm_gateway: Any,
    player_input: str,
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    candidate_action: Dict[str, Any],
) -> Dict[str, Any]:
    if llm_gateway is None:
        return {}

    prompt = build_action_intelligence_prompt(
        player_input=player_input,
        simulation_state=simulation_state,
        runtime_state=runtime_state,
        candidate_action=candidate_action,
    )

    raw_text = ""
    try:
        if hasattr(llm_gateway, "complete_json"):
            result = llm_gateway.complete_json(prompt)
            if isinstance(result, dict):
                return normalize_action_advisory(result, candidate_action)
        if hasattr(llm_gateway, "complete"):
            result = llm_gateway.complete(prompt)
            if isinstance(result, dict):
                raw_text = _safe_str(result.get("text") or result.get("content") or "")
            else:
                raw_text = _safe_str(result)
    except Exception:
        return {}

    parsed = _extract_json_object(raw_text)
    return normalize_action_advisory(parsed, candidate_action)