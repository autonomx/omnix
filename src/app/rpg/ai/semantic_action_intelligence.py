from __future__ import annotations

import json
from typing import Any, Dict, List

from app.rpg.session.turn_grounding import build_turn_grounding_packet

_ALLOWED_ACTION_TYPES = {"attack_unarmed", "attack_melee", "attack_ranged", "block", "dodge", "parry", "persuade", "intimidate", "deceive", "sneak", "investigate", "hack", "cast_spell", "use_item", "pickup_item", "drop_item", "equip_item", "unequip_item", "observe", "social_activity", "social_competition", "social_affection", "social_performance", "trade", "ritual", "exploration", "threat"}
_ALLOWED_SEMANTIC_FAMILIES = {"combat", "defense", "social", "trade", "ritual", "exploration", "stealth", "magic", "technical", "item", "threat", "observation"}
_ALLOWED_INTERACTION_MODES = {"solo", "direct", "group", "public"}
_ALLOWED_VISIBILITY = {"private", "local", "public"}
_ALLOWED_INTENSITY = {0, 1, 2, 3}
_ALLOWED_STAKES = {0, 1, 2, 3}
_ALLOWED_EFFECT_AXES = {"camaraderie", "respect", "trust", "fear", "tension", "curiosity", "suspicion", "morale"}
_ALLOWED_OBSERVER_HOOKS = {"spectacle", "conversation_seed", "crowd_attention", "authority_notice", "relationship_shift", "rumor_seed"}
_ALLOWED_SCENE_IMPACTS = {"none", "minor_focus_shift", "gathers_attention", "disrupts_flow", "changes_mood"}


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _safe_str(v: Any) -> str:
    return str(v) if v is not None else ""


def _safe_bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        lowered = v.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    if v is None:
        return default
    return bool(v)


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


def _prompt_payload(prompt: str) -> Dict[str, Any]:
    if "INPUT:\n" not in prompt:
        return {}
    try:
        return _safe_dict(json.loads(prompt.split("INPUT:\n", 1)[1]))
    except Exception:
        return {}


def _attach_first_call_diagnostics(advisory: Dict[str, Any], *, prompt: str, raw_result: Any, raw_text: str = "", source: str) -> Dict[str, Any]:
    advisory = _safe_dict(advisory)
    payload = _prompt_payload(prompt)
    diagnostics = {
        "source": source,
        "prompt": prompt,
        "prompt_preview": prompt[:4000],
        "prompt_truncated": len(prompt) > 4000,
        "turn_grounding_packet": _safe_dict(payload.get("turn_grounding_packet")),
        "normalized_result": {k: v for k, v in advisory.items() if k != "first_call_grounding_diagnostics"},
        "raw_text": _clip_text(raw_text, 4000),
        "raw_result_type": type(raw_result).__name__,
        "format_version": "first_call_grounding_diagnostics_v1",
    }
    advisory["first_call_grounding_diagnostics"] = diagnostics
    return advisory


def build_semantic_action_prompt(player_input: str, simulation_state: Dict[str, Any], runtime_state: Dict[str, Any], candidate_action: Dict[str, Any]) -> str:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)
    candidate_action = _safe_dict(candidate_action)
    grounding_packet = build_turn_grounding_packet(player_input=player_input, simulation_state=simulation_state, runtime_state=runtime_state, candidate_action=candidate_action)
    payload = {
        "player_input": _clip_text(player_input, 500),
        "turn_grounding_packet": grounding_packet,
        "allowed_action_types": sorted(_ALLOWED_ACTION_TYPES),
        "allowed_semantic_families": sorted(_ALLOWED_SEMANTIC_FAMILIES),
        "allowed_interaction_modes": sorted(_ALLOWED_INTERACTION_MODES),
        "allowed_visibility": sorted(_ALLOWED_VISIBILITY),
        "allowed_effect_axes": sorted(_ALLOWED_EFFECT_AXES),
        "allowed_observer_hooks": sorted(_ALLOWED_OBSERVER_HOOKS),
        "allowed_scene_impacts": sorted(_ALLOWED_SCENE_IMPACTS),
    }
    instructions = (
        "You are the RPG first-call semantic intent router.\n"
        "Return JSON only.\n"
        "Use the turn_grounding_packet before classifying intent. It includes current scene, active modes, recent turns, rich NPC biography/personality/speech examples, relationship, inventory, capabilities, and knowledge boundaries.\n"
        "World/runtime state is authoritative and overrides older profile memory.\n"
        "Convert freeform player intent into a bounded semantic action object.\n"
        "Do not decide success, failure, damage, XP, prices, stock, inventory mutation, quest completion, travel success, rewards, or final state.\n"
        "Do not invent absent actors. Prefer a nearby/addressed NPC id when the target role or name strongly implies one.\n"
        "For non-stateful interpretive NPC dialogue/opinion questions, set stateful false, needs_runtime_resolution false, and provide visible_response.\n"
        "For commerce, combat, travel, inventory, quests, persuasion with consequences, threats, or anything that may mutate state, set stateful true and needs_runtime_resolution true.\n"
        "Never reveal private_context or private NPC biography/inventory in visible_response.\n"
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
        '  "stateful": true,\n'
        '  "needs_runtime_resolution": true,\n'
        '  "visible_response": {"narration": string, "npc": {"speaker": string, "line": string}},\n'
        '  "reason": string\n'
        "}\n"
        "Examples:\n"
        "- 'I challenge Bran to darts' => stateful true, action_type social_competition, semantic_family social, activity_label darts\n"
        "- 'I hug Elara' => stateful true, action_type social_affection, semantic_family social, activity_label hug\n"
        "- 'I buy everyone a round' => stateful true, action_type trade or social_activity, semantic_family social, activity_label buying_drinks\n"
        "- 'Bran, what do you think about sword combat styles?' => stateful false, action_type social_activity, semantic_family social, visible_response as Bran\n"
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
    try:
        intensity = int(advisory.get("intensity", 1))
    except Exception:
        intensity = 1
    if intensity not in _ALLOWED_INTENSITY:
        intensity = 1
    try:
        stakes = int(advisory.get("stakes", 1))
    except Exception:
        stakes = 1
    if stakes not in _ALLOWED_STAKES:
        stakes = 1
    observer_hooks = []
    for value in _safe_list(advisory.get("observer_hooks"))[:4]:
        hook = _safe_str(value).strip().lower()
        if hook in _ALLOWED_OBSERVER_HOOKS and hook not in observer_hooks:
            observer_hooks.append(hook)
    social_axes = []
    for item in _safe_list(advisory.get("social_axes"))[:4]:
        item = _safe_dict(item)
        axis = _safe_str(item.get("axis")).strip().lower()
        if axis not in _ALLOWED_EFFECT_AXES:
            continue
        try:
            delta = int(item.get("delta", 0))
        except Exception:
            delta = 0
        if delta:
            social_axes.append({"axis": axis, "delta": max(-2, min(2, delta))})
    secondary_actor_ids = []
    for value in _safe_list(advisory.get("secondary_actor_ids"))[:4]:
        actor_id = _safe_str(value).strip()
        if actor_id and actor_id not in secondary_actor_ids:
            secondary_actor_ids.append(actor_id)
    scene_impact = _safe_str(advisory.get("scene_impact")).strip().lower()
    if scene_impact not in _ALLOWED_SCENE_IMPACTS:
        scene_impact = "none"
    visible_response = _safe_dict(advisory.get("visible_response"))
    normalized_visible_response = {}
    if visible_response:
        npc = _safe_dict(visible_response.get("npc"))
        normalized_visible_response = {"narration": _clip_text(visible_response.get("narration"), 500), "npc": {"speaker": _clip_text(npc.get("speaker"), 80), "line": _clip_text(npc.get("line"), 900)}}
    stateful = _safe_bool(advisory.get("stateful"), True)
    needs_runtime_resolution = _safe_bool(advisory.get("needs_runtime_resolution"), stateful)
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
        "stateful": stateful,
        "needs_runtime_resolution": needs_runtime_resolution,
        "visible_response": normalized_visible_response,
        "grounding_packet_version": "turn_grounding_packet_v1",
        "reason": _clip_text(advisory.get("reason"), 200),
    }


def get_semantic_action_advisory(llm_gateway: Any, player_input: str, simulation_state: Dict[str, Any], runtime_state: Dict[str, Any], candidate_action: Dict[str, Any]) -> Dict[str, Any]:
    if llm_gateway is None:
        return {}
    prompt = build_semantic_action_prompt(player_input, simulation_state, runtime_state, candidate_action)
    raw_text = ""
    try:
        if hasattr(llm_gateway, "complete_json"):
            result = llm_gateway.complete_json(prompt)
            if isinstance(result, dict):
                advisory = normalize_semantic_action_advisory(result, candidate_action)
                return _attach_first_call_diagnostics(advisory, prompt=prompt, raw_result=result, source="semantic_action_intelligence.complete_json")
        if hasattr(llm_gateway, "complete"):
            result = llm_gateway.complete(prompt)
            raw_text = _safe_str(result.get("text") or result.get("content") or "") if isinstance(result, dict) else _safe_str(result)
    except Exception:
        return {}
    advisory = normalize_semantic_action_advisory(_extract_json_object(raw_text), candidate_action)
    return _attach_first_call_diagnostics(advisory, prompt=prompt, raw_result=raw_text, raw_text=raw_text, source="semantic_action_intelligence.complete")
