from __future__ import annotations

import json
from typing import Any, Dict, List


_ALLOWED_ACTION_TYPES = {
    # Existing authoritative resolver buckets
    "attack_unarmed",
    "attack_melee",
    "attack_ranged",
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

    # New generic semantic-capable buckets
    "social_activity",
    "social_competition",
    "social_affection",
    "social_performance",
    "trade",
    "ritual",
    "exploration",
    "threat",
}

_ALLOWED_SEMANTIC_FAMILIES = {
    "combat",
    "defense",
    "social",
    "trade",
    "ritual",
    "exploration",
    "stealth",
    "magic",
    "technical",
    "item",
    "threat",
    "observation",
}

_ALLOWED_INTERACTION_MODES = {
    "solo",
    "direct",
    "group",
    "public",
}

_ALLOWED_VISIBILITY = {
    "private",
    "local",
    "public",
}

_ALLOWED_INTENSITY = {0, 1, 2, 3}
_ALLOWED_STAKES = {0, 1, 2, 3}
_ALLOWED_EFFECT_AXES = {
    "camaraderie",
    "respect",
    "trust",
    "fear",
    "tension",
    "curiosity",
    "suspicion",
    "morale",
}
_ALLOWED_OBSERVER_HOOKS = {
    "spectacle",
    "conversation_seed",
    "crowd_attention",
    "authority_notice",
    "relationship_shift",
    "rumor_seed",
}
_ALLOWED_SCENE_IMPACTS = {
    "none",
    "minor_focus_shift",
    "gathers_attention",
    "disrupts_flow",
    "changes_mood",
}


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _safe_str(v: Any) -> str:
    return str(v) if v is not None else ""


def _clip_text(text: Any, limit: int = 120) -> str:
    return _safe_str(text).strip()[:limit]


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


def build_semantic_action_prompt(
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
    npc_index = _safe_dict(simulation_state.get("npc_index"))
    nearby_ids = _safe_list(player_state.get("nearby_npc_ids")) or _safe_list(current_scene.get("present_npc_ids"))

    nearby_npcs: List[Dict[str, Any]] = []
    for npc_id in nearby_ids[:8]:
        npc = _safe_dict(npc_index.get(npc_id))
        if not npc:
            continue
        nearby_npcs.append({
            "npc_id": _safe_str(npc.get("id") or npc_id),
            "name": _clip_text(npc.get("name"), 60),
            "role": _clip_text(npc.get("role"), 60),
            "location_id": _safe_str(npc.get("location_id")),
        })

    payload = {
        "player_input": _clip_text(player_input, 240),
        "candidate_action": {
            "action_type": _safe_str(candidate_action.get("action_type")),
            "target_id": _safe_str(candidate_action.get("target_id")),
            "target_name": _safe_str(candidate_action.get("target_name")),
            "difficulty": _safe_str(candidate_action.get("difficulty")),
        },
        "scene": {
            "scene_id": _safe_str(current_scene.get("scene_id")),
            "location_id": _safe_str(current_scene.get("location_id")),
            "summary": _clip_text(current_scene.get("summary"), 160),
        },
        "player": {
            "location_id": _safe_str(player_state.get("location_id")),
            "stats": _safe_dict(player_state.get("stats")),
            "skills": _safe_dict(player_state.get("skills")),
        },
        "nearby_npcs": nearby_npcs,
        "allowed_action_types": sorted(_ALLOWED_ACTION_TYPES),
        "allowed_semantic_families": sorted(_ALLOWED_SEMANTIC_FAMILIES),
        "allowed_interaction_modes": sorted(_ALLOWED_INTERACTION_MODES),
        "allowed_visibility": sorted(_ALLOWED_VISIBILITY),
        "allowed_effect_axes": sorted(_ALLOWED_EFFECT_AXES),
        "allowed_observer_hooks": sorted(_ALLOWED_OBSERVER_HOOKS),
        "allowed_scene_impacts": sorted(_ALLOWED_SCENE_IMPACTS),
    }

    instructions = (
        "You are an RPG semantic action interpreter.\n"
        "Return JSON only.\n"
        "Do not decide success, failure, damage, XP, or narration.\n"
        "Convert freeform player intent into a bounded semantic action object.\n"
        "Do not invent absent actors.\n"
        "Prefer a nearby NPC id when the target role or name strongly implies one.\n"
        "Use open-ended activity_label values, but only bounded enums for family/mode/visibility/observer hooks.\n"
        "Schema:\n"
        "{\n"
        '  "action_type": string,\n'
        '  "semantic_family": string,\n'
        '  "interaction_mode": string,\n'
        '  "activity_label": string,\n'
        '  "target_id": string,\n'
        '  "target_name": string,\n'
        '  "secondary_actor_ids": [string],\n'
        '  "visibility": string,\n'
        '  "intensity": 0,\n'
        '  "stakes": 0,\n'
        '  "social_axes": [{"axis":"camaraderie","delta":1}],\n'
        '  "observer_hooks": [string],\n'
        '  "scene_impact": string,\n'
        '  "reason": string\n'
        "}\n"
        "Examples:\n"
        "- 'I challenge Bran to darts' => action_type social_competition, semantic_family social, activity_label darts\n"
        "- 'I hug Elara' => action_type social_affection, semantic_family social, activity_label hug\n"
        "- 'I buy everyone a round' => action_type trade or social_activity, semantic_family social, activity_label buying_drinks\n"
        "- 'I perform a song' => action_type social_performance, semantic_family social, activity_label song\n"
    )

    return instructions + "\nINPUT:\n" + json.dumps(payload, sort_keys=True)


def normalize_semantic_action_advisory(advisory: Dict[str, Any], candidate_action: Dict[str, Any]) -> Dict[str, Any]:
    advisory = _safe_dict(advisory)
    candidate_action = _safe_dict(candidate_action)

    action_type = _safe_str(advisory.get("action_type")).strip().lower()
    if action_type not in _ALLOWED_ACTION_TYPES:
        action_type = _safe_str(candidate_action.get("action_type")).strip().lower()
    if action_type not in _ALLOWED_ACTION_TYPES:
        action_type = "observe"

    semantic_family = _safe_str(advisory.get("semantic_family")).strip().lower()
    if semantic_family not in _ALLOWED_SEMANTIC_FAMILIES:
        # derive from action_type
        if action_type in {"social_activity", "social_competition", "social_affection", "social_performance", "persuade", "deceive"}:
            semantic_family = "social"
        elif action_type in {"trade"}:
            semantic_family = "trade"
        elif action_type in {"ritual"}:
            semantic_family = "ritual"
        elif action_type in {"exploration", "investigate", "observe"}:
            semantic_family = "exploration"
        elif action_type in {"intimidate", "threat"}:
            semantic_family = "threat"
        elif action_type in {"sneak"}:
            semantic_family = "stealth"
        elif action_type in {"hack"}:
            semantic_family = "technical"
        elif action_type in {"pickup_item", "drop_item", "equip_item", "unequip_item", "use_item"}:
            semantic_family = "item"
        else:
            semantic_family = "observation"

    interaction_mode = _safe_str(advisory.get("interaction_mode")).strip().lower()
    if interaction_mode not in _ALLOWED_INTERACTION_MODES:
        interaction_mode = "direct" if _safe_str(advisory.get("target_id")) else "solo"

    visibility = _safe_str(advisory.get("visibility")).strip().lower()
    if visibility not in _ALLOWED_VISIBILITY:
        visibility = "local"

    intensity = advisory.get("intensity", 1)
    try:
        intensity = int(intensity)
    except Exception:
        intensity = 1
    if intensity not in _ALLOWED_INTENSITY:
        intensity = 1

    stakes = advisory.get("stakes", 1)
    try:
        stakes = int(stakes)
    except Exception:
        stakes = 1
    if stakes not in _ALLOWED_STAKES:
        stakes = 1

    observer_hooks: List[str] = []
    for value in _safe_list(advisory.get("observer_hooks"))[:4]:
        hook = _safe_str(value).strip().lower()
        if hook in _ALLOWED_OBSERVER_HOOKS and hook not in observer_hooks:
            observer_hooks.append(hook)

    social_axes: List[Dict[str, Any]] = []
    for item in _safe_list(advisory.get("social_axes"))[:4]:
        item = _safe_dict(item)
        axis = _safe_str(item.get("axis")).strip().lower()
        if axis not in _ALLOWED_EFFECT_AXES:
            continue
        try:
            delta = int(item.get("delta", 0))
        except Exception:
            delta = 0
        if delta == 0:
            continue
        if delta > 2:
            delta = 2
        if delta < -2:
            delta = -2
        social_axes.append({"axis": axis, "delta": delta})

    secondary_actor_ids: List[str] = []
    for value in _safe_list(advisory.get("secondary_actor_ids"))[:4]:
        actor_id = _safe_str(value).strip()
        if actor_id and actor_id not in secondary_actor_ids:
            secondary_actor_ids.append(actor_id)

    scene_impact = _safe_str(advisory.get("scene_impact")).strip().lower()
    if scene_impact not in _ALLOWED_SCENE_IMPACTS:
        scene_impact = "none"

    return {
        "action_type": action_type,
        "semantic_family": semantic_family,
        "interaction_mode": interaction_mode,
        "activity_label": _clip_text(advisory.get("activity_label"), 64).lower().replace(" ", "_"),
        "target_id": _safe_str(advisory.get("target_id") or candidate_action.get("target_id")).strip(),
        "target_name": _clip_text(advisory.get("target_name") or candidate_action.get("target_name"), 80),
        "secondary_actor_ids": secondary_actor_ids,
        "visibility": visibility,
        "intensity": intensity,
        "stakes": stakes,
        "social_axes": social_axes,
        "observer_hooks": observer_hooks,
        "scene_impact": scene_impact,
        "reason": _clip_text(advisory.get("reason"), 200),
    }


def get_semantic_action_advisory(
    llm_gateway: Any,
    player_input: str,
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    candidate_action: Dict[str, Any],
) -> Dict[str, Any]:
    if llm_gateway is None:
        return {}

    prompt = build_semantic_action_prompt(
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
                return normalize_semantic_action_advisory(result, candidate_action)
        if hasattr(llm_gateway, "complete"):
            result = llm_gateway.complete(prompt)
            if isinstance(result, dict):
                raw_text = _safe_str(result.get("text") or result.get("content") or "")
            else:
                raw_text = _safe_str(result)
    except Exception:
        return {}

    parsed = _extract_json_object(raw_text)
    return normalize_semantic_action_advisory(parsed, candidate_action)