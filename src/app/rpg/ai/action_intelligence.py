from __future__ import annotations

import json
from typing import Any, Dict, List

from app.rpg.session.turn_grounding import build_turn_grounding_packet

_ALLOWED_ACTION_TYPES = {
    "attack_melee", "attack_ranged", "attack_unarmed", "block", "dodge", "parry",
    "persuade", "intimidate", "deceive", "sneak", "investigate", "hack",
    "cast_spell", "use_item", "pickup_item", "drop_item", "equip_item", "unequip_item",
    "observe", "social_activity", "social_competition", "social_affection",
    "social_performance", "trade", "ritual", "exploration", "threat",
}
_ALLOWED_DIFFICULTIES = {"trivial", "easy", "normal", "hard", "extreme"}
_ALLOWED_SKILLS = {
    "swordsmanship", "archery", "firearms", "defense", "stealth", "persuasion",
    "intimidation", "investigation", "magic", "hacking", "performance", "barter", "ritual",
}


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


def _clip_text(text: Any, limit: int = 240) -> str:
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


def _attach_first_call_diagnostics(
    advisory: Dict[str, Any],
    *,
    prompt: str,
    raw_result: Any,
    raw_text: str = "",
    source: str,
    provider_called: bool = False,
    provider_error: str = "",
    parse_ok: bool | None = None,
) -> Dict[str, Any]:
    advisory = _safe_dict(advisory)
    payload = _prompt_payload(prompt)
    raw_text = _safe_str(raw_text)
    parsed_visible_response = bool(_safe_dict(advisory.get("visible_response")))
    if parse_ok is None:
        parse_ok = bool(_safe_dict(raw_result)) if isinstance(raw_result, dict) else bool(_extract_json_object(raw_text))
    provider_response_empty = provider_called and not raw_text.strip() and not parse_ok
    provider_malformed_json = provider_called and bool(raw_text.strip()) and not parse_ok
    if provider_error:
        provider_status = "provider_error"
    elif provider_response_empty:
        provider_status = "empty_response"
    elif provider_malformed_json:
        provider_status = "malformed_json"
    elif parse_ok:
        provider_status = "valid_json"
    elif provider_called:
        provider_status = "called_without_parseable_json"
    else:
        provider_status = "not_called"
    diagnostics = {
        "source": source,
        "prompt": prompt,
        "prompt_preview": prompt[:4000],
        "prompt_truncated": len(prompt) > 4000,
        "turn_grounding_packet": _safe_dict(payload.get("turn_grounding_packet")),
        "normalized_result": {k: v for k, v in advisory.items() if k != "first_call_grounding_diagnostics"},
        "raw_text": _clip_text(raw_text, 4000),
        "raw_text_length": len(raw_text),
        "raw_result_type": type(raw_result).__name__,
        "provider_requested": True,
        "provider_called": provider_called,
        "provider_status": provider_status,
        "provider_error": provider_error,
        "provider_response_empty": provider_response_empty,
        "provider_parse_ok": bool(parse_ok),
        "provider_malformed_json": provider_malformed_json,
        "provider_visible_response_present": parsed_visible_response,
        "provider_non_stateful": not _safe_bool(advisory.get("stateful"), True),
        "provider_needs_runtime_resolution": _safe_bool(advisory.get("needs_runtime_resolution"), True),
        "format_version": "first_call_grounding_diagnostics_v1",
    }
    advisory["first_call_grounding_diagnostics"] = diagnostics
    return advisory


def _complete_raw_text(llm_gateway: Any, prompt: str) -> tuple[Any, str, str]:
    if hasattr(llm_gateway, "complete"):
        result = llm_gateway.complete(prompt)
        if isinstance(result, dict):
            raw_text = _safe_str(result.get("text") or result.get("content") or "")
        else:
            raw_text = _safe_str(result)
        return result, raw_text, "action_intelligence.complete"
    if hasattr(llm_gateway, "complete_json"):
        result = llm_gateway.complete_json(prompt)
        raw_text = json.dumps(result, ensure_ascii=False, sort_keys=True) if isinstance(result, dict) and result else ""
        return result, raw_text, "action_intelligence.complete_json"
    return {}, "", "action_intelligence.no_provider_method"


def build_action_intelligence_prompt(
    player_input: str,
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    candidate_action: Dict[str, Any],
) -> str:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)
    candidate_action = _safe_dict(candidate_action)
    grounding_packet = build_turn_grounding_packet(
        player_input=player_input,
        simulation_state=simulation_state,
        runtime_state=runtime_state,
        candidate_action=candidate_action,
    )
    payload = {
        "player_input": _clip_text(player_input, 500),
        "turn_grounding_packet": grounding_packet,
        "allowed_action_types": sorted(_ALLOWED_ACTION_TYPES),
        "allowed_difficulties": sorted(_ALLOWED_DIFFICULTIES),
        "allowed_skills": sorted(_ALLOWED_SKILLS),
    }
    instructions = (
        "You are the RPG first-call action-intent extraction layer.\n"
        "Return JSON only.\n"
        "Use the provided turn_grounding_packet before classifying intent.\n"
        "The packet may contain rich NPC biography, personality, speech examples, relationship, inventory, capabilities, and knowledge boundaries.\n"
        "World/runtime state is authoritative and overrides older memory/profile data.\n"
        "Do not decide outcomes, damage, XP, hit chance, prices, stock, inventory mutation, quest completion, travel success, or rewards.\n"
        "You may only suggest bounded action metadata for deterministic runtime.\n"
        "If the input is non-stateful interpretive NPC dialogue, mark stateful false and include a visible_response candidate.\n"
        "If the input might mutate state, buy/sell items, start combat, travel, accept/complete quests, change relationships, or reveal facts, mark stateful true and needs_runtime_resolution true.\n"
        "Never reveal private_context or private NPC biography/inventory in visible_response.\n"
        "Schema:\n"
        "{\n"
        '  "action_type": string,\n'
        '  "difficulty": string,\n'
        '  "skill_id": string,\n'
        '  "intent_tags": [string],\n'
        '  "narrative_goal": string,\n'
        '  "target_id": string,\n'
        '  "target_name": string,\n'
        '  "stateful": true,\n'
        '  "needs_runtime_resolution": true,\n'
        '  "visible_response": {"narration": string, "npc": {"speaker": string, "line": string}},\n'
        '  "reason": string\n'
        "}\n"
        "Prefer the candidate_action action_type unless the text clearly implies a better allowed action.\n"
    )
    return instructions + "\nINPUT:\n" + json.dumps(payload, sort_keys=True)


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
    visible_response = _safe_dict(advisory.get("visible_response"))
    normalized_visible_response = {}
    if visible_response:
        npc = _safe_dict(visible_response.get("npc"))
        normalized_visible_response = {
            "narration": _clip_text(visible_response.get("narration"), 500),
            "npc": {"speaker": _clip_text(npc.get("speaker"), 80), "line": _clip_text(npc.get("line"), 900)},
        }
    stateful = _safe_bool(advisory.get("stateful"), True)
    needs_runtime_resolution = _safe_bool(advisory.get("needs_runtime_resolution"), stateful)
    return {
        "action_type": action_type,
        "difficulty": difficulty,
        "skill_id": skill_id,
        "intent_tags": intent_tags,
        "narrative_goal": _clip_text(advisory.get("narrative_goal"), 120),
        "target_id": _safe_str(advisory.get("target_id") or candidate_action.get("target_id") or candidate_action.get("npc_id")).strip(),
        "target_name": _clip_text(advisory.get("target_name"), 80),
        "stateful": stateful,
        "needs_runtime_resolution": needs_runtime_resolution,
        "visible_response": normalized_visible_response,
        "grounding_packet_version": "turn_grounding_packet_v1",
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
    metadata["stateful"] = _safe_bool(advisory.get("stateful"), True)
    metadata["needs_runtime_resolution"] = _safe_bool(advisory.get("needs_runtime_resolution"), metadata["stateful"])
    metadata["visible_response_if_no_runtime_needed"] = _safe_dict(advisory.get("visible_response"))
    metadata["grounding_packet_version"] = _safe_str(advisory.get("grounding_packet_version") or "turn_grounding_packet_v1")
    metadata["first_call_grounding_diagnostics"] = _safe_dict(advisory.get("first_call_grounding_diagnostics"))
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
    prompt = build_action_intelligence_prompt(player_input, simulation_state, runtime_state, candidate_action)
    raw_result: Any = {}
    raw_text = ""
    source = "action_intelligence.complete"
    parsed: Dict[str, Any] = {}
    provider_error = ""
    try:
        raw_result, raw_text, source = _complete_raw_text(llm_gateway, prompt)
        parsed = _safe_dict(raw_result) if source.endswith("complete_json") else _extract_json_object(raw_text)
    except Exception as exc:
        provider_error = f"{type(exc).__name__}: {exc}"
    advisory = normalize_action_advisory(parsed, candidate_action)
    return _attach_first_call_diagnostics(
        advisory,
        prompt=prompt,
        raw_result=raw_result,
        raw_text=raw_text,
        source=source,
        provider_called=not source.endswith("no_provider_method"),
        provider_error=provider_error,
        parse_ok=bool(parsed),
    )
