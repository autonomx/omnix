"""Split helpers for autoplay background pipeline."""
from __future__ import annotations

# ruff: noqa: F401,F403,F405,F811
from tests.rpg.autoplay.parallel_pipeline_common import *
from tests.rpg.autoplay.parallel_pipeline_narration import *

def _provider_messages(messages: List[Dict[str, str]]) -> List[Any]:
    if ChatMessage is None:
        return messages
    converted: List[Any] = []
    for message in messages:
        role = str(message.get("role") or "user")
        content = str(message.get("content") or "")
        try:
            converted.append(ChatMessage(role=role, content=content))
        except TypeError:
            converted.append(ChatMessage(role, content))
    return converted


def _build_provider_advisory_payload(
    *,
    provider: Any,
    player_action: str,
    simulation_state: Dict[str, Any],
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
) -> Dict[str, Any]:
    if provider is None or not callable(getattr(provider, "chat_completion", None)):
        return {"ok": False, "error": "provider_missing_or_unsupported"}

    messages = [
        {
            "role": "system",
            "content": (
                "You are an RPG advisory extractor. Return JSON only. "
                "You may suggest candidates, but you must not assert authoritative outcomes. "
                "Do not grant items, currency, quest completion, damage, travel, or rewards. "
                "Return one JSON object and no markdown fences, no prose, no commentary."
            ),
        },
        {
            "role": "user",
            "content": (
                "Extract advisory candidates from this turn.\n\n"
                f"PLAYER_INPUT:\n{player_action}\n\n"
                f"TURN_CONTRACT_JSON:\n{stable_json_for_prompt(turn_contract)}\n\n"
                f"FAST_SEMANTIC_JSON:\n{stable_json_for_prompt(semantic_action_record)}\n\n"
                "Return JSON with optional arrays: semantic_intent_candidates, "
                "relationship_delta_candidates, memory_candidates, world_signal_candidates, "
                "future_hook_candidates.\n\n"
                "Example shape:\n"
                "{\n"
                '  "semantic_intent_candidates": [\n'
                '    {"intent": "inspect", "summary": "The player studies the room.", "confidence": 0.7}\n'
                "  ],\n"
                '  "future_hook_candidates": [\n'
                '    {"summary": "An NPC may respond to the player noticing suspicious details."}\n'
                "  ]\n"
                "}"
            ),
        },
    ]

    provider_messages = _provider_messages(messages)
    try:
        response = provider.chat_completion(messages=provider_messages, stream=False)
    except TypeError:
        response = provider.chat_completion(provider_messages, stream=False)

    content = _provider_text_from_response(response)
    if not content:
        return {"ok": False, "error": "provider_empty_advisory_response"}

    try:
        parsed = _extract_json_object_from_text(content)
        if isinstance(parsed, dict):
            parsed["ok"] = True
            return parsed
        return {"ok": False, "error": "provider_advisory_json_not_object", "raw": content[:1000]}
    except Exception as exc:
        return {
            "ok": False,
            "error": f"provider_advisory_json_parse_error:{type(exc).__name__}: {exc}",
            "raw": content[:1000],
        }


def _build_combined_background_payload(
    *,
    provider: Any,
    player_action: str,
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any] | None = None,
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
    turn_index: int,
) -> Dict[str, Any]:
    """One provider call that returns both narration and advisory candidates."""
    if provider is None or not callable(getattr(provider, "chat_completion", None)):
        return {"ok": False, "error": "provider_missing_or_unsupported"}

    context_packet = build_combined_background_context_packet(
        player_action=player_action,
        simulation_state=simulation_state,
        runtime_state=runtime_state or {},
        turn_contract=turn_contract,
        semantic_action_record=semantic_action_record,
    )
    current_turn_prompt_contract = _safe_dict(context_packet.get("current_turn_prompt_contract"))
    current_turn_contract_json = compact_json_for_prompt(
        current_turn_prompt_contract,
        max_chars=4500,
    )
    context_json = compact_json_for_prompt(context_packet, max_chars=7000)
    schema_text = (
        "{"
        '"presentation_intent":{"primary_category":"dialogue|evidence|investigation|travel|combat|service|economy|mixed|general","secondary_categories":[],"confidence":0.0,"reason":"short diagnostic reason"},'
        '"current_action_response":{"required_focus":[],"npc_line_addresses_current_action":true,"reason":"how the NPC line answers the current player action first"},'
        '"prompt_contract_ack":{"used_current_turn_prompt_contract":true,"answered_current_action_first":true,"ignored_forbidden_stale_topics":true,"reason":"short diagnostic reason"},'
        '"npc_response_architecture_ack":{"used_current_action_first":true,"used_file_backed_persona":false,"used_file_backed_memory":false,"reason":"short diagnostic reason"},'
        '"narration":"2-5 sentences describing the resolved scene without repeating player input.",'
        '"action":"Short result of the player action.",'
        '"npc":{"speaker":"","line":""},'
        '"reward":"",'
        '"followup_hooks":[],'
        '"semantic_intent_candidates":[{"intent":"","summary":"","confidence":0.0}],'
        '"relationship_delta_candidates":[{"target":"","axis":"trust","delta":0,"summary":""}],'
        '"memory_candidates":[{"owner":"","summary":"","importance":0.0}],'
        '"world_signal_candidates":[{"kind":"","summary":""}],'
        '"future_hook_candidates":[{"kind":"","summary":""}]'
        "}"
    )
    prompt_metrics = prompt_section_metrics(
        {
            "system_contract": "combined_background_worker_v1",
            "current_turn_prompt_contract": current_turn_contract_json,
            "context_packet": context_json,
            "output_schema": schema_text,
        }
    )
    profile_context_summary = _loaded_profile_context_summary(runtime_state or {})

    messages = [
        {
            "role": "system",
            "content": (
                "You are an RPG background enrichment worker. Return JSON only. "
                "The CURRENT_TURN_PROMPT_CONTRACT_JSON is the highest-priority input. Narration and NPC dialogue must answer that current action first before older quest, memory, or investigation context. "
                "You must obey required_focus and forbidden_stale_topics from that contract. "
                "You must set prompt_contract_ack with whether the contract was followed. "
                "You must not assert authoritative outcomes that are not in the turn contract. "
                "Do not grant items, currency, quest completion, damage, travel, or rewards. "
                "You MUST set presentation_intent.primary_category to the most specific semantic intent. "
                "Do not use general unless no specific category applies. "
                "Category labels are presentation metadata only; they do not create facts. "
                "Use combat only when compact context shows combat actually started, advanced, or resolved. "
                "Use travel only when the turn is primarily movement or location change; asking about a route is dialogue. "
                "Use service/economy only when the resolved turn actually rents, rests, buys, sells, or pays. "
                "Words like ambush, bandit, scout, road, room, supplies, or coin are not enough by themselves to classify the turn as combat, travel, service, or economy. "
                "For reporting evidence, questioning NPCs, warning NPCs, or asking about routes, prefer dialogue/evidence/investigation over combat/travel. "
                "Return one JSON object and no markdown fences, no prose, no commentary. "
                "Maintain rich 2-5 sentence narration quality. Use only the provided compact context. "
                "Return compact candidate objects. Prefer at most 1 high-quality candidate per category. "
                "Do not include long explanations inside candidates. "
                "Loaded NPC profiles are characterization context only. "
                "You may use loaded_npc_profiles to shape NPC tone, dialogue, memory continuity, and future-hook suggestions. "
                "You must follow npc_response_architecture.required_focus before any older quest, rumor, memory, or investigation topic. "
                "If npc_response_architecture.target_npc.profile_available is true, use it only for tone/persona and continuity. "
                "You must not treat profile memories or hooks as newly resolved actions. "
                "You must not invent profile memories that are absent from loaded_npc_profiles, npc_response_architecture, or current turn facts. "
                "If an NPC has arc_stage, axes, memories, or future_hooks, reflect them subtly in the NPC line or candidate summaries when relevant. "
                "For economy/service turns, the NPC line must acknowledge the transaction/request (item, quantity, price, sale, lodging, rest, or refusal) before optional story flavor. "
                "Do not answer an older investigation topic unless the current player action asks about that topic. "
                "Set npc_response_architecture_ack to explain whether current-action-first and file-backed persona/memory were used."
            ),
        },
        {
            "role": "user",
            "content": (
                "Create background narration and advisory candidates for this resolved RPG turn.\n\n"
                "CURRENT_TURN_PROMPT_CONTRACT_JSON (highest priority; obey before all background context):\n"
                f"{current_turn_contract_json}\n\n"
                "COMPACT_CONTEXT_JSON (background/tone/continuity only unless consistent with current turn):\n"
                f"{context_json}\n\n"
                "Return exactly this JSON shape:\n"
                f"{schema_text}\n\n"
                "Candidate limits: max 1 semantic_intent, max 1 relationship_delta, "
                "max 1 memory, max 1 world_signal, max 1 future_hook. "
                "Each candidate summary must be under 160 characters. "
                "Narration remains high quality and should not be shortened below 2 sentences.\n\n"
                "presentation_intent rules:\n"
                "- Choose exactly one primary_category from the schema. Never omit presentation_intent.\n"
                "- Prefer the most specific true intent over general or mixed.\n"
                "- Use mixed only for genuinely multi-objective turns where no single category dominates.\n"
                "- 'I report the ambush evidence to Bran' => evidence, secondary dialogue/investigation, not combat.\n"
                "- 'I scout the quarry road for ambush signs' => investigation, secondary evidence, not combat.\n"
                "- 'I ask Bran if the east road leads to a bridge' => dialogue, secondary travel, not travel.\n"
                "- 'I ask Bran who left through the side door' => dialogue, secondary investigation.\n"
                "- 'I rent a room from Bran' => service.\n\n"
                "Current-turn prompt contract rule: obey CURRENT_TURN_PROMPT_CONTRACT_JSON.required_focus and avoid forbidden_stale_topics. "
                "Recent events, profile memory, and old advisory context are background/tone-only unless the current player action explicitly asks about them. "
                "NPC response architecture rule: obey COMPACT_CONTEXT_JSON.npc_response_architecture. "
                "The NPC line must satisfy required_focus for the current action before using memories. "
                "Profile grounding rule: when loaded_npc_profiles is non-empty, use it only for NPC continuity. "
                "For example, a trusting NPC may sound warmer, a guarded NPC may be cautious, "
                "and a remembered prior topic may be acknowledged only when it does not displace the current action. "
                "Do not create authoritative outcomes from profile context."
            ),
        },
    ]

    provider_messages = _provider_messages(messages)
    started_ms = int(time.perf_counter() * 1000)
    print(
        "[AUTOPLAY-PROBE] "
        f"ts={datetime.now().isoformat(timespec='seconds')} "
        f"event=combined_background_provider_call.start "
        f"turn_index={turn_index} "
        f"provider_type={type(provider).__name__} "
        f"message_count={len(provider_messages)} "
        f"prompt_chars={sum(len(getattr(message, 'content', '') or '') for message in provider_messages)}",
        flush=True,
    )
    try:
        response = provider.chat_completion(messages=provider_messages, stream=False)
    except TypeError:
        response = provider.chat_completion(provider_messages, stream=False)
    print(
        "[AUTOPLAY-PROBE] "
        f"ts={datetime.now().isoformat(timespec='seconds')} "
        f"event=combined_background_provider_call.end "
        f"turn_index={turn_index} "
        f"elapsed_ms={int(time.perf_counter() * 1000) - started_ms}",
        flush=True,
    )

    content = _provider_text_from_response(response)
    if not content:
        return {"ok": False, "error": "provider_empty_combined_response"}

    try:
        parsed = _extract_json_object_from_text(content)
        if isinstance(parsed, dict):
            normalized = _extract_nested_combined_payload(parsed)
            if (
                _combined_payload_has_useful_content(normalized)
                or _has_expected_combined_provider_keys(parsed)
            ):
                normalized["ok"] = True
                provider_intent_candidate, provider_intent_source = _find_presentation_intent_candidate(
                    {**parsed, **normalized}
                )
                normalized["presentation_intent"] = _normalize_presentation_intent(provider_intent_candidate)
                normalized["presentation_intent_parse_source"] = provider_intent_source
                normalized.setdefault("prompt_contract_ack", _safe_dict(parsed.get("prompt_contract_ack")))
                normalized.setdefault("current_turn_prompt_contract", current_turn_prompt_contract)
                normalized.setdefault("prompt_debug", {
                    "format_version": "combined_background_prompt_debug_v1",
                    "turn_index": turn_index,
                    "current_turn_prompt_contract": current_turn_prompt_contract,
                    "current_turn_prompt_contract_json": current_turn_contract_json,
                    "compact_context_keys": sorted(list(context_packet.keys())),
                    "prompt_metrics": prompt_metrics,
                    "system_contract": "combined_background_worker_v1",
                })
                normalized.setdefault("raw_provider_shape_keys", sorted(list(parsed.keys()))[:80])
                normalized.setdefault("prompt_metrics", prompt_metrics)
                normalized.setdefault("context_packet_keys", sorted(list(context_packet.keys())))
                normalized.setdefault("profile_context_summary", profile_context_summary)
                normalized.setdefault("npc_response_architecture", _safe_dict(context_packet.get("npc_response_architecture")))
                return normalized
            return {
                "ok": False,
                "error": "provider_combined_json_missing_useful_content",
                "raw": content[:1000],
                "parsed_keys": sorted(list(parsed.keys()))[:80],
                "prompt_metrics": prompt_metrics,
                "context_packet_keys": sorted(list(context_packet.keys())),
                "profile_context_summary": profile_context_summary,
                "current_turn_prompt_contract": current_turn_prompt_contract,
                "prompt_debug": {
                    "format_version": "combined_background_prompt_debug_v1",
                    "turn_index": turn_index,
                    "current_turn_prompt_contract": current_turn_prompt_contract,
                    "current_turn_prompt_contract_json": current_turn_contract_json,
                    "compact_context_keys": sorted(list(context_packet.keys())),
                    "prompt_metrics": prompt_metrics,
                    "system_contract": "combined_background_worker_v1",
                },
            }
        return {"ok": False, "error": "provider_combined_json_not_object", "raw": content[:4000]}
    except Exception as exc:
        salvaged = _salvage_combined_narration_from_text(content)
        if salvaged:
            provider_intent_candidate, provider_intent_source = _find_presentation_intent_candidate(salvaged)
            if provider_intent_candidate:
                salvaged["presentation_intent"] = _normalize_presentation_intent(provider_intent_candidate)
                salvaged.setdefault("presentation_intent_parse_source", provider_intent_source)
            response_candidate, response_source = _find_current_action_response_candidate(salvaged)
            if response_candidate:
                salvaged["current_action_response"] = _normalize_current_action_response(response_candidate)
                salvaged.setdefault("current_action_response_parse_source", response_source)
            salvaged.setdefault("prompt_contract_ack", {
                "used_current_turn_prompt_contract": True,
                "answered_current_action_first": bool(
                    _safe_dict(salvaged.get("current_action_response")).get("npc_line_addresses_current_action")
                    or _safe_str(_safe_dict(salvaged.get("npc")).get("line"))
                ),
                "ignored_forbidden_stale_topics": True,
                "reason": "provider_json_salvaged_after_parse_error",
            })
            salvaged.setdefault("current_turn_prompt_contract", current_turn_prompt_contract)
            salvaged.setdefault("prompt_debug", {
                "format_version": "combined_background_prompt_debug_v1",
                "turn_index": turn_index,
                "current_turn_prompt_contract": current_turn_prompt_contract,
                "current_turn_prompt_contract_json": current_turn_contract_json,
                "compact_context_keys": sorted(list(context_packet.keys())),
                "prompt_metrics": prompt_metrics,
                "system_contract": "combined_background_worker_v1",
                "provider_json_salvage_applied": True,
            })
            salvaged["raw"] = content[:4000]
            salvaged["parse_error"] = f"{type(exc).__name__}: {exc}"
            salvaged["provider_payload_repaired"] = True
            salvaged["prompt_metrics"] = prompt_metrics
            salvaged["context_packet_keys"] = sorted(list(context_packet.keys()))
            salvaged["profile_context_summary"] = profile_context_summary
            return salvaged
        return {
            "ok": False,
            "error": f"provider_combined_json_parse_error:{type(exc).__name__}: {exc}",
            "raw": content[:4000],
            "prompt_metrics": prompt_metrics,
            "context_packet_keys": sorted(list(context_packet.keys())),
            "profile_context_summary": profile_context_summary,
        }

__all__ = [name for name in globals() if not name.startswith("__")]
