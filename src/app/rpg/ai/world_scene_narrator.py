"""Phase 5 — LLM Scene Engine + NPC Behavior

Turns structured scenes into narrative experiences:
    Scene → Narrative → NPC reactions → Dialogue → Player response

Provides prompt building, narrative generation, and response parsing
for the scene narration pipeline.

Phase 5.1 fixes:
- JSON-structured LLM output enforcement
- NPC state injection (memory, beliefs, relationships)
- Choice → action binding
- Scene action hooks
"""

from __future__ import annotations

import json
import logging
import re
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from app.rpg.memory.npc_memory_recall import memory_reference_is_backed

# Phase 8: player-facing encounter view
from app.rpg.player import build_encounter_view

logger = logging.getLogger(__name__)

_ACTIVE_NARRATIONS = set()

NARRATION_JSON_FORMAT_VERSION = "rpg_narration_v2"

NARRATION_JSON_SCHEMA_HINT = {
    "format_version": NARRATION_JSON_FORMAT_VERSION,
    "narration": "string",
    "action": "string",
    "npc": {
        "speaker": "string",
        "line": "string",
    },
    "reward": "string",
    "followup_hooks": [],
}


def _extract_llm_text(response):
    """Extract text from provider response in various formats."""
    if isinstance(response, str):
        return response.strip()

    if not isinstance(response, dict):
        return ""

    # OpenAI / Cerebras format
    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]

        # Chat format
        msg = first.get("message")
        if isinstance(msg, dict):
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()

        # Text format fallback
        text = first.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()

    # Direct text fallback
    if isinstance(response.get("text"), str):
        return response["text"].strip()

    return ""


def _llm_text(llm_gateway, prompt, *, context=None, on_chunk=None):
    """Call the LLM gateway and return the response as a clean string."""
    logger.info("[RPG LLM GATEWAY] Calling LLM with prompt length: %d, context keys: %s", len(prompt), list(context.keys()) if context else [])
    gateway_call = getattr(llm_gateway, "call", None)
    gateway_generate = getattr(llm_gateway, "generate", None)
    gateway_generate_stream = getattr(llm_gateway, "generate_stream", None)

    if on_chunk:
        # Try streaming if callback provided
        chunks = []
        try:
            print("[RPG][LLM] calling provider.stream")
            if callable(gateway_call):
                events = gateway_call("generate_stream", prompt, context=context or {})
            elif callable(gateway_generate_stream):
                events = gateway_generate_stream(prompt, context=context or {})
            else:
                raise AttributeError("gateway has no streaming interface")

            for event in events:
                piece = _safe_str(_safe_dict(event).get("text"))
                if piece:
                    chunks.append(piece)
                    on_chunk(piece)
            print("[RPG][LLM] stream completed, chunks:", len(chunks))
            return _extract_llm_text("".join(chunks).strip())
        except Exception as exc:
            print("[RPG][LLM] stream failed:", repr(exc))
            logger.exception("[RPG LLM GATEWAY] Streaming failed, falling back to non-streaming")
            if chunks:
                return _extract_llm_text("".join(chunks).strip())

    # Fallback to non-streaming
    try:
        print("[RPG][LLM] calling provider.generate")
        print("[ACTIVE PROVIDER]", llm_gateway)
        if callable(gateway_call):
            response = gateway_call("generate", prompt, context=context or {})
        elif callable(gateway_generate):
            response = gateway_generate(prompt, context=context or {})
        elif callable(gateway_generate_stream):
            chunks = []
            for event in gateway_generate_stream(prompt, context=context or {}):
                piece = _safe_str(_safe_dict(event).get("text"))
                if piece:
                    chunks.append(piece)
            response = "".join(chunks).strip()
        else:
            raise AttributeError("gateway has no generate or call interface")
        print("[RPG][LLM] raw response:", repr(response)[:500])
        logger.info("[RPG LLM GATEWAY] Received response type: %s, length: %d", type(response), len(str(response)) if response else 0)
    except Exception as exc:
        print("[RPG][LLM] generate failed:", repr(exc))
        logger.exception("[RPG LLM GATEWAY] LLM call failed")
        raise RuntimeError(
            f"live_llm_required_but_llm_failed: provider_exception: {repr(exc)}"
        )
    if response is None:
        logger.warning("[RPG LLM GATEWAY] LLM returned None")
        return ""
    # Extract text from response dict or return string directly
    return _extract_llm_text(response)


# ---------------------------------------------------------------------------
# Phase 6.5 — social context helpers
# ---------------------------------------------------------------------------
def _attach_social_context(scene, simulation_state):
    scene = dict(scene or {})
    simulation_state = simulation_state or {}
    social_state = simulation_state.get("social_state") or {}

    scene["active_rumors"] = [
        dict(item)
        for item in (simulation_state.get("active_rumors") or [])[:3]
    ]
    scene["active_alliances"] = [
        dict(item)
        for item in (social_state.get("alliances") or [])
        if item.get("status") == "active"
    ][:3]
    scene["faction_positions"] = {
        key: dict(value)
        for key, value in sorted((social_state.get("group_positions") or {}).items())
    }
    return scene


# ---------------------------------------------------------------------------
# Phase 6 — NPC mind context helpers
# ---------------------------------------------------------------------------

def _safe_str_p6(value):
    if value is None:
        return ""
    return str(value)


def _attach_npc_mind_context(actor, simulation_state):
    """Attach Phase 6 NPC mind context to an actor dict."""
    actor = dict(actor or {})
    simulation_state = simulation_state or {}

    npc_id = _safe_str_p6(actor.get("id"))
    npc_minds = simulation_state.get("npc_minds") or {}
    mind = npc_minds.get(npc_id) or {}

    if isinstance(mind, dict):
        actor["memory_summary"] = ((mind.get("memory") or {}).get("entries") or [])[:5]
        actor["belief_summary"] = ((mind.get("beliefs") or {}).get("beliefs") or {})
        actor["active_goals"] = ((mind.get("goals") or {}).get("goals") or [])[:5]
        actor["last_decision"] = mind.get("last_decision") or {}

    return actor


_NARRATION_MAX_MARKDOWN = 300


def _safe_str(value: Any) -> str:
    return str(value) if value is not None else ""


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _title_case_token(value: Any) -> str:
    text = _safe_str(value).strip()
    if not text:
        return ""
    return text.replace("_", " ").strip().title()


def _force_live_llm_required(narration_context: Dict[str, Any]) -> bool:
    narration_context = _safe_dict(narration_context)
    runtime_settings = _safe_dict(narration_context.get("runtime_settings"))
    performance = _safe_dict(narration_context.get("performance"))
    return bool(
        narration_context.get("require_live_llm_narration")
        or runtime_settings.get("require_live_llm_narration")
        or performance.get("require_live_llm_narration")
    )


def _build_ambient_conversation_line(narration_context: Dict[str, Any]) -> str:
    narration_context = _safe_dict(narration_context)
    beat = _safe_dict(narration_context.get("beat"))

    speaker_id = _safe_str(beat.get("speaker_id")).strip() or "someone"
    speaker = _title_case_token(speaker_id) or "Someone"

    summary = _safe_str(beat.get("summary")).strip()
    stance = _safe_str(beat.get("stance")).strip().lower()
    addressed_to = [_title_case_token(x) for x in _safe_list(beat.get("addressed_to")) if _safe_str(x).strip()]
    mentions = [_title_case_token(x) for x in _safe_list(beat.get("mentions")) if _safe_str(x).strip()]

    summary = summary.rstrip(".!? ").strip()
    if not summary:
        summary = "says something under their breath"

    prefix = f"{speaker}: "
    if stance in {"warning", "cautious", "worried"}:
        prefix = f"{speaker} lowers their voice. "
    elif stance in {"challenge", "angry", "threat"}:
        prefix = f"{speaker} snaps back. "
    elif stance in {"friendly", "warm", "supportive"}:
        prefix = f"{speaker} says warmly, "
    elif stance in {"secretive", "whisper", "hushed"}:
        prefix = f"{speaker} whispers, "

    # Address target naturally if present.
    if addressed_to:
        if len(addressed_to) == 1:
            target_phrase = f" to {addressed_to[0]}"
        else:
            target_phrase = f" to {', '.join(addressed_to[:2])}"
    else:
        target_phrase = ""

    line = prefix
    if prefix.endswith(": "):
        line = f"{speaker}{target_phrase}: {summary}"
    else:
        line = f"{prefix}{summary}"

    # Soft mention enrichment, bounded and presentation-only.
    if mentions:
        mention = mentions[0]
        summary_lower = summary.lower()
        if mention.lower() not in summary_lower:
            line = f"{line} ({mention})"

    return line.strip()


def _bound_text(value: Any, limit: int = 180) -> str:
    text = _safe_str(value).strip()
    if len(text) > limit:
        return text[:limit].rstrip() + "..."
    return text


def _clean_npc_dialogue_line(value: Any) -> str:
    """Clean NPC dialogue without presentation truncation."""
    text = _safe_str(value).strip()
    if not text:
        return ""

    text = text.strip().strip('"').strip("'").strip()
    if text.startswith("{") or text.startswith("["):
        return ""

    # Hard safety cap only. Do not insert ellipses into normal dialogue.
    max_chars = 1200
    if len(text) > max_chars:
        text = text[:max_chars].rstrip()
        if text and not text.endswith((".", "!", "?", '"', "'")):
            text += "."

    return text


def _is_accommodation_request(narration_context: Dict[str, Any]) -> bool:
    narration_context = _safe_dict(narration_context)
    turn_contract = _safe_dict(narration_context.get("turn_contract"))
    semantic_action = _safe_dict(turn_contract.get("semantic_action"))
    action = _safe_dict(turn_contract.get("action"))
    metadata = _safe_dict(action.get("metadata"))
    nested_semantic = _safe_dict(metadata.get("semantic_action"))

    haystack = " ".join(
        [
            _safe_str(semantic_action.get("activity_label")),
            _safe_str(semantic_action.get("reason")),
            _safe_str(semantic_action.get("action_type")),
            _safe_str(nested_semantic.get("activity_label")),
            _safe_str(nested_semantic.get("reason")),
            _safe_str(nested_semantic.get("action_type")),
        ]
    ).lower()

    return any(
        token in haystack
        for token in (
            "room",
            "rent",
            "accommodation",
            "lodging",
            "inn",
            "request_accommodation",
            "asking_to_rent",
        )
    )


def _has_authoritative_accommodation_offer(narration_context: Dict[str, Any]) -> bool:
    narration_context = _safe_dict(narration_context)
    resolved = _safe_dict(narration_context.get("resolved_result"))
    turn_contract = _safe_dict(narration_context.get("turn_contract"))
    resolved_from_contract = _safe_dict(
        turn_contract.get("resolved_result")
        or turn_contract.get("resolved_action")
    )

    for source in (resolved, resolved_from_contract):
        action_metadata = _safe_dict(source.get("action_metadata"))
        effect_result = _safe_dict(source.get("effect_result"))
        service_effects = _safe_dict(effect_result.get("service_effects"))

        if _safe_str(action_metadata.get("transaction_kind")):
            return True
        if _safe_str(action_metadata.get("price_source")):
            return True
        if service_effects:
            return True
        if _safe_str(source.get("service_id") or source.get("room_id") or source.get("offer_id")):
            return True

    return False


def _ground_accommodation_npc_line(line: str, narration_context: Dict[str, Any]) -> str:
    if not _is_accommodation_request(narration_context):
        return line

    if _has_authoritative_accommodation_offer(narration_context):
        return line

    lower = _safe_str(line).lower()
    invented_terms = (
        # Availability / offer claims
        "vacant room",
        "vacant rooms",
        "available room",
        "available rooms",
        "room available",
        "rooms available",
        "we do have",
        "i do have",
        "i've got",
        "ive got",
        "we've got",
        "we have a room",
        "i have a room",
        "got a room",
        "got a cozy",
        "cozy little room",
        "vacancies",
        "vacancy",
        "no vacancies",
        "haven't had any vacancies",
        "havent had any vacancies",
        "might have somethin",
        "might have something",
        "something for you",
        "somethin' for you",

        # Scene movement / transition claims
        "follow me",
        "come with me",
        "let me show you",
        "show you the room",

        # Specific room/location facts
        "top floor",
        "above the inn",
        "down the hall",
        "down the corridor",
        "best view",
        "garden out back",
        "stable accommodations",
        "accommodations in town",

        # Price / transaction claims
        "what'll it cost",
        "what will it cost",
        "cost you",
        "price",
        "five silver",
        "silver",
        "gold",
        "copper",

        # Quality/assignment claims
        "perfect for a traveler",
        "perfect for you",
        "just right for",
        "settle you in",
    )

    if not any(term in lower for term in invented_terms):
        return line

    return (
        "A room, you say? Let me check what I can offer before we settle the details."
    )


def _service_result_from_context(narration_context: Dict[str, Any]) -> Dict[str, Any]:
    narration_context = _safe_dict(narration_context)
    turn_contract = _safe_dict(narration_context.get("turn_contract"))

    # 1. Prefer direct authoritative/applied service result.
    #
    # Runtime service purchase mutation updates resolved_result. Older copies
    # under turn_contract.service_result or action.metadata.service_result may
    # still say purchase_ready. The narrator must use the applied copy.
    direct_service = _safe_dict(narration_context.get("service_result"))
    if direct_service.get("matched"):
        return direct_service

    direct_resolved = _safe_dict(narration_context.get("resolved_result"))
    direct_resolved_service = _safe_dict(direct_resolved.get("service_result"))
    if direct_resolved_service.get("matched"):
        return direct_resolved_service

    # 2. Then use resolved contract state.
    resolved = _safe_dict(
        turn_contract.get("resolved_result")
        or turn_contract.get("resolved_action")
    )
    resolved_service = _safe_dict(resolved.get("service_result"))
    if resolved_service.get("matched"):
        return resolved_service

    # 3. Then fallback to top-level contract state.
    direct = _safe_dict(turn_contract.get("service_result"))
    if direct.get("matched"):
        return direct

    # 4. Then fallback to action metadata.
    action = _safe_dict(turn_contract.get("action"))
    action_nested = _safe_dict(action.get("service_result"))
    if action_nested.get("matched"):
        return action_nested

    metadata = _safe_dict(action.get("metadata"))
    metadata_nested = _safe_dict(metadata.get("service_result"))
    if metadata_nested.get("matched"):
        return metadata_nested

    return {}

def _recalled_service_memories_from_context(narration_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    narration_context = _safe_dict(narration_context)
    memories = narration_context.get("recalled_service_memories")
    if isinstance(memories, list):
        return [_safe_dict(memory) for memory in memories if _safe_dict(memory)]
    return []


def _format_recalled_service_memories_for_prompt(narration_context: Dict[str, Any]) -> str:
    memories = _recalled_service_memories_from_context(narration_context)
    if not memories:
        return "None."

    lines: List[str] = []
    for memory in memories[:5]:
        summary = _safe_str(memory.get("summary"))
        kind = _safe_str(memory.get("kind"))
        sentiment = _safe_str(memory.get("sentiment"))
        service_kind = _safe_str(memory.get("service_kind"))
        if not summary:
            continue
        details = ", ".join(
            part
            for part in [
                f"kind={kind}" if kind else "",
                f"service={service_kind}" if service_kind else "",
                f"sentiment={sentiment}" if sentiment else "",
            ]
            if part
        )
        if details:
            lines.append(f"- {summary} ({details})")
        else:
            lines.append(f"- {summary}")

    return "\n".join(lines) if lines else "None."


def _recalled_npc_memories_from_context(narration_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    narration_context = _safe_dict(narration_context)
    memories = narration_context.get("recalled_npc_memories")
    if isinstance(memories, list):
        return [_safe_dict(memory) for memory in memories if _safe_dict(memory)]
    return []


def _format_recalled_npc_memories_for_prompt(narration_context: Dict[str, Any]) -> str:
    memories = _recalled_npc_memories_from_context(narration_context)
    if not memories:
        return "None."

    lines: List[str] = []
    for memory in memories[:6]:
        summary = _safe_str(memory.get("summary"))
        kind = _safe_str(memory.get("kind"))
        sentiment = _safe_str(memory.get("sentiment"))
        if not summary:
            continue
        suffix = ", ".join(part for part in [kind, sentiment] if part)
        lines.append(f"- {summary}" + (f" ({suffix})" if suffix else ""))

    return "\n".join(lines) if lines else "None."


def _conversation_result_from_context(narration_context: Dict[str, Any]) -> Dict[str, Any]:
    narration_context = _safe_dict(narration_context)
    direct = _safe_dict(narration_context.get("conversation_result"))
    if direct:
        return direct
    resolved = _safe_dict(narration_context.get("resolved_result"))
    return _safe_dict(resolved.get("conversation_result"))


def _format_conversation_beat_for_prompt(narration_context: Dict[str, Any]) -> str:
    conversation = _conversation_result_from_context(narration_context)
    if not conversation.get("triggered"):
        return "None."
    beat = _safe_dict(conversation.get("beat"))
    topic = _safe_dict(conversation.get("topic"))
    participation = _safe_dict(conversation.get("player_participation"))
    speaker = _safe_str(beat.get("speaker_name"))
    listener = _safe_str(beat.get("listener_name"))
    line = _safe_str(beat.get("line"))
    topic_title = _safe_str(topic.get("title") or beat.get("topic"))
    if not line:
        return "None."
    mode = _safe_str(participation.get("mode") or conversation.get("participation_mode") or "overheard")
    return f'{speaker} speaks to {listener} about {topic_title} [{mode}]: "{line}"'


def _apply_grounded_conversation_beat(
    payload: Dict[str, Any],
    narration_context: Dict[str, Any],
) -> None:
    conversation = _conversation_result_from_context(narration_context)
    if not conversation.get("triggered"):
        return
    beat = _safe_dict(conversation.get("beat"))
    speaker = _safe_str(beat.get("speaker_name"))
    line = _safe_str(beat.get("line"))
    if not speaker or not line:
        return

    # Preserve the normal narration/action, but force the NPC line to the
    # deterministic conversation beat. The LLM can frame the scene but cannot
    # invent the actual NPC-to-NPC line.
    payload["npc"] = {
        "speaker": speaker,
        "line": line,
    }
    participation = _safe_dict(conversation.get("player_participation"))
    if participation.get("pending_response"):
        hooks = payload.get("followup_hooks")
        if not isinstance(hooks, list):
            hooks = []
        prompt = _safe_str(participation.get("prompt"))
        if prompt:
            hooks.append(prompt)
        payload["followup_hooks"] = hooks


def _line_has_prior_memory_reference(line: str) -> bool:
    lower = _safe_str(line).lower()
    if not lower:
        return False
    markers = (
        "remember",
        "last time",
        "again",
        "earlier",
        "still short",
        "short on coin",
        "same as before",
        "as i told you",
        "as i said",
        "you came by",
        "you asked",
        "you bought",
        "you tried",
    )
    return any(marker in lower for marker in markers)


def _memory_reference_is_backed(line: str, narration_context: Dict[str, Any]) -> bool:
    if not _line_has_prior_memory_reference(line):
        return True

    memories = _recalled_service_memories_from_context(narration_context)
    if not memories:
        return False

    lower = _safe_str(line).lower()
    for memory in memories:
        summary = _safe_str(memory.get("summary")).lower()
        kind = _safe_str(memory.get("kind"))
        if kind and kind in lower:
            return True
        if "short" in lower and _safe_str(memory.get("blocked_reason")) == "insufficient_funds":
            return True
        if "coin" in lower and _safe_str(memory.get("blocked_reason")) == "insufficient_funds":
            return True
        if "bought" in lower and kind == "service_purchase":
            return True
        if "asked" in lower and kind == "service_inquiry":
            return True
        if summary and any(token in summary for token in lower.split() if len(token) > 5):
            return True

    specific_claim_terms = ("short", "coin", "bought", "paid", "purchased", "failed")
    if not any(term in lower for term in specific_claim_terms):
        return True

    return False


def _strip_unbacked_memory_reference_from_npc_line(
    line: str,
    narration_context: Dict[str, Any],
) -> str:
    service_backed = _memory_reference_is_backed(line, narration_context)
    npc_backed = memory_reference_is_backed(
        line,
        _recalled_npc_memories_from_context(narration_context),
    )
    if service_backed or npc_backed:
        return line

    grounded_line = _service_grounded_npc_line(narration_context)
    if grounded_line:
        return grounded_line

    return "What can I help you with?"


def _strip_service_meta_language(text: str, narration_context: Dict[str, Any]) -> str:
    text = _safe_str(text)
    if not text:
        return text

    lower = text.lower()
    service_result = _service_result_from_context(narration_context)
    if not service_result.get("matched"):
        return text

    provider_name = _safe_str(service_result.get("provider_name") or "The provider")
    purchase = _safe_dict(service_result.get("purchase"))
    service_application = _safe_dict(narration_context.get("service_application"))
    blocked_reason = _safe_str(
        service_application.get("blocked_reason")
        or purchase.get("blocked_reason")
    )

    meta_markers = (
        "the system confirms",
        "the request to purchase",
        "is processed by",
        "the transaction is processed",
        "the intent to buy",
    )
    if not any(marker in lower for marker in meta_markers):
        return text

    if blocked_reason == "insufficient_funds":
        return f"{provider_name} checks the available offer and current coin, then finds the purchase cannot be completed."

    if blocked_reason == "offer_not_found":
        return f"{provider_name} checks the available offers and finds no matching item or service."

    if _safe_str(service_result.get("kind")) == "service_purchase":
        return f"{provider_name} checks the available offer and current terms."

    return text


def _service_offer_label_with_price(offer: Dict[str, Any]) -> str:
    offer = _safe_dict(offer)
    label = _safe_str(offer.get("label") or offer.get("offer_id")).strip()
    price = _safe_dict(offer.get("price"))

    parts = []
    gold = int(price.get("gold") or 0)
    silver = int(price.get("silver") or 0)
    copper = int(price.get("copper") or 0)

    if gold:
        parts.append(f"{gold} gold")
    if silver:
        parts.append(f"{silver} silver")
    if copper:
        parts.append(f"{copper} copper")

    if parts:
        return f"{label} for {', '.join(parts)}"
    return label


def _join_natural(items: List[str]) -> str:
    items = [item for item in items if _safe_str(item).strip()]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} or {items[1]}"
    return f"{', '.join(items[:-1])}, or {items[-1]}"


def _travel_result_from_context(narration_context: Dict[str, Any]) -> Dict[str, Any]:
    narration_context = _safe_dict(narration_context)
    resolved = _safe_dict(narration_context.get("resolved_result"))
    travel = _safe_dict(resolved.get("travel_result"))
    if travel:
        return travel
    turn_contract = _safe_dict(narration_context.get("turn_contract"))
    resolved = _safe_dict(turn_contract.get("resolved_result") or turn_contract.get("resolved_action"))
    return _safe_dict(resolved.get("travel_result"))


def _grounded_travel_narration(narration_context: Dict[str, Any]) -> str:
    travel = _travel_result_from_context(narration_context)
    if not travel.get("matched"):
        return ""
    if not travel.get("applied"):
        exits = _safe_dict(travel.get("available_exits"))
        if exits:
            return "No clear route matches that destination from here."
        return "There is no available route from here."
    to_location = _safe_dict(travel.get("to_location"))
    name = _safe_str(to_location.get("name") or travel.get("to_location_id"))
    return f"You arrive at {name}."


def _grounded_travel_action(narration_context: Dict[str, Any]) -> str:
    travel = _travel_result_from_context(narration_context)
    if not travel.get("matched"):
        return ""
    if travel.get("applied"):
        to_location = _safe_dict(travel.get("to_location"))
        name = _safe_str(to_location.get("name") or travel.get("to_location_id"))
        return f"You travel to {name}."
    return "No available route matches that destination."


def _final_grounded_service_action_text(
    action_text: str,
    narration_context: Dict[str, Any],
) -> str:
    """Final authority pass for Result/action text.

    This runs after generic sanitization because phrases like
    "The attempt fails." can be introduced late by fallback cleanup. Service
    purchase failures must remain specific and deterministic.
    """
    service_result = _service_result_from_context(narration_context)
    if not service_result.get("matched"):
        return action_text

    if _safe_str(service_result.get("kind")) != "service_purchase":
        return action_text

    purchase = _safe_dict(service_result.get("purchase"))
    service_application = _safe_dict(narration_context.get("service_application"))
    status = _safe_str(service_result.get("status"))
    blocked_reason = _safe_str(
        service_application.get("blocked_reason")
        or purchase.get("blocked_reason")
    )

    if status == "blocked" or blocked_reason == "insufficient_funds":
        grounded = _service_grounded_action_result(narration_context)
        if grounded:
            return grounded

    if status == "purchase_offer_not_found" or blocked_reason == "offer_not_found":
        grounded = _service_grounded_action_result(narration_context)
        if grounded:
            return grounded

    generic = _safe_str(action_text).strip().lower()
    if generic in {
        "the attempt fails",
        "the attempt fails.",
        "you fail",
        "you fail.",
        "it fails",
        "it fails.",
    }:
        grounded = _service_grounded_action_result(narration_context)
        if grounded:
            return grounded

    return action_text


def _service_grounded_action_result(narration_context: Dict[str, Any]) -> str:
    service_result = _service_result_from_context(narration_context)
    if not service_result:
        return ""

    provider_name = _safe_str(service_result.get("provider_name") or "The provider").strip()
    kind = _safe_str(service_result.get("kind"))
    status = _safe_str(service_result.get("status"))

    if kind == "service_purchase":
        purchase = _safe_dict(service_result.get("purchase"))
        service_application = _safe_dict(narration_context.get("service_application"))
        blocked_reason = _safe_str(
            service_application.get("blocked_reason")
            or purchase.get("blocked_reason")
        )

        if status == "purchase_offer_not_found" or blocked_reason == "offer_not_found":
            if provider_name:
                return f"{provider_name} cannot find a matching available offer."
            return "No matching available offer is available."

        purchase_applied = (
            _safe_str(service_result.get("status")) == "purchased"
            or bool(purchase.get("applied"))
            or bool(service_application.get("applied"))
        )

        if purchase_applied:
            return f"{provider_name} completes the purchase."
        if status == "purchase_ready":
            return f"{provider_name} is ready to complete the purchase."
        if status == "blocked" or blocked_reason == "insufficient_funds":
            return f"{provider_name} names the price, but you do not have enough coin."

    if status == "offers_available":
        return f"{provider_name} checks the available options."

    if status == "no_registered_offers":
        return f"{provider_name} has no available offer for that request."

    return f"{provider_name} considers the service request."


def _service_grounded_npc_line(narration_context: Dict[str, Any]) -> str:
    service_result = _service_result_from_context(narration_context)
    if not service_result:
        return ""

    kind = _safe_str(service_result.get("kind"))
    status = _safe_str(service_result.get("status"))
    offers = [_safe_dict(offer) for offer in _safe_list(service_result.get("offers"))]

    if kind == "service_purchase":
        purchase = _safe_dict(service_result.get("purchase"))
        service_application = _safe_dict(narration_context.get("service_application"))
        blocked_reason = _safe_str(
            service_application.get("blocked_reason")
            or purchase.get("blocked_reason")
        )

        if status == "purchase_offer_not_found" or blocked_reason == "offer_not_found":
            return "I do not have that listed among my available offers."

        purchase_applied = (
            _safe_str(service_result.get("status")) == "purchased"
            or bool(purchase.get("applied"))
            or bool(service_application.get("applied"))
        )
        selected_offer_id = _safe_str(service_result.get("selected_offer_id"))
        selected = {}
        for offer in offers:
            if _safe_str(offer.get("offer_id")) == selected_offer_id:
                selected = offer
                break

        selected_label = _safe_str(selected.get("label") or selected_offer_id or "that").strip()

        if purchase_applied:
            if selected_label and selected_label != "that":
                return f"Done. {selected_label} is settled."
            return "Done. The purchase is settled."

        if status == "purchase_ready":
            return f"I can settle {selected_label} once you confirm the purchase."

        if status == "blocked":
            price = _safe_dict(purchase.get("price"))
            price_text = _service_offer_label_with_price({"label": selected_label, "price": price})
            return f"{price_text} is the price, but you do not have enough coin."

    if status == "offers_available" and offers:
        offer_texts = [_service_offer_label_with_price(offer) for offer in offers]
        joined = _join_natural(offer_texts)
        if joined:
            return f"I can offer {joined}."

    if status == "no_registered_offers":
        return "I do not have an available offer for that right now."

    return "Let me check what I can offer before we settle the details."


def _normalized_text_for_compare(value: Any) -> str:
    text = _safe_str(value).strip().lower()
    return " ".join(text.split())


def _fallback_non_service_narration(narration_context: Dict[str, Any]) -> str:
    narration_context = _safe_dict(narration_context)
    player_input = _safe_str(narration_context.get("player_input"))
    turn_contract = _safe_dict(narration_context.get("turn_contract"))
    resolved = _safe_dict(
        narration_context.get("resolved_result")
        or turn_contract.get("resolved_result")
        or turn_contract.get("resolved_action")
    )
    action_type = _safe_str(resolved.get("action_type") or _safe_dict(turn_contract.get("action")).get("action_type"))
    target_name = _safe_str(resolved.get("target_name") or _safe_dict(turn_contract.get("action")).get("target_name"))
    outcome = _safe_str(resolved.get("outcome"))

    if target_name and action_type in {"social_activity", "persuade", "investigate"}:
        if outcome == "success":
            return f"{target_name} gives the request their attention and responds."
        if outcome == "partial":
            return f"{target_name} considers the request, but the answer comes with some uncertainty."
        return f"{target_name} considers the request."

    if action_type:
        return "The action resolves against the current situation."

    if player_input:
        return "The moment shifts in response to your action."

    return "The scene continues."


def _sanitize_repeated_player_input_narration(
    payload: Dict[str, Any],
    narration_context: Dict[str, Any],
) -> None:
    narration = _safe_str(payload.get("narration"))
    player_input = _safe_str(narration_context.get("player_input"))
    if not narration or not player_input:
        return

    if _normalized_text_for_compare(narration) == _normalized_text_for_compare(player_input):
        payload["narration"] = _fallback_non_service_narration(narration_context)


def _naturalize_service_debug_language(text: str) -> str:
    text = _safe_str(text)
    if not text:
        return text
    replacements = {
        "registered shop goods options": "available goods",
        "registered lodging options": "available lodging options",
        "registered meal options": "available meal options",
        "registered paid information options": "available information options",
        "registered repair options": "available repair options",
        "registered offers": "available offers",
        "registered offer": "available offer",
        "Registered shop goods options": "available goods",
        "Registered lodging options": "available lodging options",
        "Registered meal options": "available meal options",
        "Registered paid information options": "available information options",
        "Registered repair options": "available repair options",
        "Registered offers": "available offers",
        "Registered offer": "available offer",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _service_grounded_narration_text(narration_context: Dict[str, Any]) -> str:
    service_result = _service_result_from_context(narration_context)
    if not service_result:
        return ""

    provider_name = _safe_str(service_result.get("provider_name") or "The provider").strip()
    service_kind = _safe_str(service_result.get("service_kind")).replace("_", " ").strip()
    status = _safe_str(service_result.get("status"))
    purchase = _safe_dict(service_result.get("purchase"))
    service_application = _safe_dict(narration_context.get("service_application"))
    blocked_reason = _safe_str(
        service_application.get("blocked_reason")
        or purchase.get("blocked_reason")
    )

    if (
        _safe_str(service_result.get("kind")) == "service_purchase"
        and (
            status == "purchase_offer_not_found"
            or blocked_reason == "offer_not_found"
        )
    ):
        return f"{provider_name} checks the available offers and finds no matching item or service."

    if status == "offers_available":
        if service_kind:
            return f"{provider_name} looks over the available {service_kind} options."
        return f"{provider_name} looks over the available options."

    if status == "offers_available":
        if service_kind:
            return f"{provider_name} looks over the registered {service_kind} options."
        return f"{provider_name} looks over the registered service options."

    if status == "blocked":
        return f"{provider_name} checks the available offer and current coin, then finds the purchase cannot be completed."

    if status == "purchased":
        return f"{provider_name} completes the registered service purchase."

    if status == "purchase_ready":
        return f"{provider_name} confirms the selected available offer."

    return f"{provider_name} considers the service request."


def _service_narration_needs_grounding(text: str) -> bool:
    lower = _safe_str(text).lower()
    if not lower:
        return False

    repeated_action_phrases = (
        "as you ask",
        "you ask",
        "you asked",
        "you inquire",
        "you inquired",
        "about a room",
        "room to rent",
        "what she sells",
        "heard any rumors",
        "buy a torch",
        "from elara",
        "from bran",
        "request for lodging",
        "seeking shelter",
        "seeking lodging",
        "as you address",
        "address bran",
        "travelers seeking shelter",
    )
    return any(phrase in lower for phrase in repeated_action_phrases)


def _service_claim_needs_grounding(text: str) -> bool:
    lower = _safe_str(text).lower()
    if not lower:
        return False

    claim_terms = (
        "i have",
        "i've got",
        "ive got",
        "we have",
        "we've got",
        "rooms",
        "room",
        "cheap",
        "not cheap",
        "price",
        "cost",
        "available",
        "offer",
        "offers",
        "buy",
        "sell",
        "sells",
        "food",
        "meal",
        "stew",
        "ale",
        "drink",
        "rumor",
        "rumour",
        "repair",
        "torch",
        "rope",
        "done",
        "yours",
        "settled",
        "complete",
        "completed",
        "purchase",
        "paid",
        "settle",
        "can settle",
        "once you confirm",
        "confirm the purchase",
        "complete the purchase",
        "ready to complete",
        "ready to settle",
    )
    return any(term in lower for term in claim_terms)


def _ground_action_result_text(action_text: str, narration_context: Dict[str, Any]) -> str:
    text = _safe_str(action_text).strip()
    if not text:
        return text

    lower_text = text.lower()

    service_result = _service_result_from_context(narration_context)
    if service_result.get("matched"):
        if lower_text in {
            "the attempt fails.",
            "the attempt fails",
            "you fail.",
            "you fail",
            "it fails.",
            "it fails",
        }:
            grounded = _service_grounded_action_result(narration_context)
            if grounded:
                return grounded

        purchase = _safe_dict(service_result.get("purchase"))
        service_application = _safe_dict(narration_context.get("service_application"))
        service_status = _safe_str(service_result.get("status"))
        blocked_reason = _safe_str(
            service_application.get("blocked_reason")
            or purchase.get("blocked_reason")
        )

        if (
            _safe_str(service_result.get("kind")) == "service_purchase"
            and (
                service_status == "blocked"
                or blocked_reason == "insufficient_funds"
            )
        ):
            grounded = _service_grounded_action_result(narration_context)
            if grounded:
                return grounded

        if (
            _safe_str(service_result.get("kind")) == "service_purchase"
            and (
                service_status == "purchase_offer_not_found"
                or blocked_reason == "offer_not_found"
            )
        ):
            grounded = _service_grounded_action_result(narration_context)
            if grounded:
                return grounded

        if (
            _safe_str(service_result.get("kind")) == "service_purchase"
            and (
                _safe_str(service_result.get("status")) == "purchased"
                or bool(purchase.get("applied"))
                or bool(service_application.get("applied"))
            )
        ):
            grounded = _service_grounded_action_result(narration_context)
            if grounded:
                return grounded

        lower_service_text = text.lower()
        repeats_service_action = (
            lower_service_text.startswith("you ")
            or "you ask" in lower_service_text
            or "you inquire" in lower_service_text
            or "you request" in lower_service_text
            or "renting a room" in lower_service_text
            or "from bran" in lower_service_text
            or "from elara" in lower_service_text
            or "what she sells" in lower_service_text
            or "heard any rumors" in lower_service_text
        )
        if repeats_service_action:
            grounded = _service_grounded_action_result(narration_context)
            if grounded:
                return grounded

    lower = text.lower()

    repeats_player_action = any(
        phrase in lower
        for phrase in (
            "you approach",
            "you ask",
            "you inquire",
            "you request",
            "with a hopeful glint",
            "if he has a room",
            "if they have a room",
            "has a room to rent",
        )
    )

    if repeats_player_action and _is_accommodation_request(narration_context):
        return "Bran considers your request."

    return text


def _player_input_action_text(narration_context: Dict[str, Any]) -> str:
    """Return the visible authoritative player-action text."""
    narration_context = _safe_dict(narration_context)
    turn_contract = _safe_dict(narration_context.get("turn_contract"))
    narration_brief = _safe_dict(turn_contract.get("narration_brief"))
    semantic_action = _safe_dict(turn_contract.get("semantic_action"))

    text = _first_nonempty(
        narration_context.get("player_input"),
        turn_contract.get("player_input"),
        narration_brief.get("summary"),
        semantic_action.get("player_input"),
        _safe_dict(narration_context.get("last_player_action")).get("text"),
    )
    text = _strip_basic_markdown(text)
    if not text:
        return ""

    lowered = text.lower()
    replacements = (
        ("i am ", "you are "),
        ("i'm ", "you are "),
        ("i ask ", "you ask "),
        ("i tell ", "you tell "),
        ("i say ", "you say "),
        ("i want ", "you want "),
        ("i try ", "you try "),
        ("i attempt ", "you attempt "),
        ("i punch ", "you punch "),
        ("i attack ", "you attack "),
        ("i ", "you "),
    )
    for prefix, replacement in replacements:
        if lowered.startswith(prefix):
            text = replacement + text[len(prefix):]
            break
    else:
        if not lowered.startswith("you "):
            text = "you " + text

    text = " ".join(text.split()).strip()
    return text[:1].upper() + text[1:]


def _build_authoritative_action_line(narration_context: Dict[str, Any]) -> str:
    action = _player_input_action_text(narration_context)
    if not action:
        return ""
    return f"Action: {action}"


def _titleize_action(action_type: str) -> str:
    value = _safe_str(action_type).strip().replace("_", " ")
    return value[:1].upper() + value[1:] if value else "Action"


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = _safe_str(value).strip()
        if text:
            return text
    return ""


def _extract_text_lines(text: str) -> List[str]:
    lines = []
    for part in _safe_str(text).splitlines():
        part = part.strip()
        if part:
            lines.append(part)
    return lines


def _normalize_speaker_block(npc_value: Any) -> Dict[str, Any]:
    npc_value = _safe_dict(npc_value) if isinstance(npc_value, dict) else {"text": _safe_str(npc_value).strip()}
    return {
        "speaker_id": _safe_str(npc_value.get("speaker_id") or npc_value.get("npc_id")).strip(),
        "name": _safe_str(npc_value.get("name")).strip(),
        "text": _bound_text(npc_value.get("text"), 180),
        "emotion": _safe_str(npc_value.get("emotion")).strip(),
        "portrait": _safe_str(npc_value.get("portrait")).strip(),
        "role": _safe_str(npc_value.get("role")).strip(),
    }


def _build_safe_prompt_context(scene: Dict[str, Any], narration_context: Dict[str, Any]) -> Dict[str, Any]:
    scene = _safe_dict(scene)
    narration_context = _safe_dict(narration_context)
    resolved = _safe_dict(narration_context.get("resolved_result"))
    xp_result = _safe_dict(narration_context.get("xp_result"))
    skill_xp_result = _safe_dict(narration_context.get("skill_xp_result"))

    return {
        "player_input": _bound_text(narration_context.get("player_input"), 120),
        "action_type": _safe_str(narration_context.get("action_type")).strip(),
        "action_result": _bound_text(
            _first_nonempty(
                resolved.get("message"),
                resolved.get("summary"),
                resolved.get("result_text"),
            ),
            140,
        ),
        "target_name": _first_nonempty(
            _safe_dict(resolved.get("combat_result")).get("target_name"),
            resolved.get("target_name"),
            resolved.get("npc_name"),
            resolved.get("target_id"),
        ),
        "damage": int(_safe_dict(resolved.get("combat_result")).get("damage", resolved.get("damage", 0)) or 0),
        "player_xp": int(xp_result.get("player_xp", 0) or 0),
        "skill_xp_awards": {
            k: int(v or 0)
            for k, v in sorted(_safe_dict(skill_xp_result.get("awards")).items())
            if int(v or 0) > 0
        },
        "level_up": bool(_safe_list(narration_context.get("level_up"))),
        "scene_title": _safe_str(scene.get("title")).strip(),
        "location_name": _first_nonempty(scene.get("location_name"), scene.get("location_id"), scene.get("scene_id")),
    }


def _build_speaker_turns(parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    parsed = _safe_dict(parsed)
    npc = _normalize_speaker_block(parsed.get("npc"))
    turns: List[Dict[str, Any]] = []

    narrator_text = " ".join(
        filter(
            None,
            [
                _safe_str(parsed.get("narrator")).strip(),
                _safe_str(parsed.get("action")).strip(),
            ],
        )
    ).strip()
    if narrator_text:
        turns.append({
            "speaker_id": "narrator",
            "name": "Narrator",
            "text": _bound_text(narrator_text, 180),
        })
    if npc.get("text"):
        turns.append(npc)
    return turns


def _extract_json_object_from_text(text: str) -> Dict[str, Any]:
    text = _safe_str(text).strip()
    if not text:
        return {}

    candidates = [text]
    normalized_quotes = text.replace("\\'", "'")
    if normalized_quotes != text:
        candidates.append(normalized_quotes)

    # Fast path: raw JSON
    for candidate in candidates:
        try:
            value = json.loads(candidate)
            return value if isinstance(value, dict) else {}
        except Exception:
            pass

    # Fenced code block path
    if "```" in text:
        blocks = text.split("```")
        for block in blocks:
            candidate = block.strip()
            if candidate.lower().startswith("json"):
                candidate = candidate[4:].strip()
            if not candidate:
                continue
            candidate_variants = [candidate]
            normalized_candidate = candidate.replace("\\'", "'")
            if normalized_candidate != candidate:
                candidate_variants.append(normalized_candidate)
            for candidate_variant in candidate_variants:
                try:
                    value = json.loads(candidate_variant)
                    return value if isinstance(value, dict) else {}
                except Exception:
                    continue

    # Loose substring path: first balanced {...}
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start:end + 1]
        candidate_variants = [candidate]
        normalized_candidate = candidate.replace("\\'", "'")
        if normalized_candidate != candidate:
            candidate_variants.append(normalized_candidate)
        for candidate_variant in candidate_variants:
            try:
                value = json.loads(candidate_variant)
                return value if isinstance(value, dict) else {}
            except Exception:
                pass

    return {}


def _normalize_narration_json(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(payload)
    npc = _safe_dict(payload.get("npc"))

    return {
        "format_version": _safe_str(payload.get("format_version")).strip() or NARRATION_JSON_FORMAT_VERSION,
        "narration": _safe_str(payload.get("narration")).strip(),
        "action": _safe_str(payload.get("action")).strip(),
        "npc": {
            "speaker": _safe_str(npc.get("speaker")).strip(),
            "line": _safe_str(npc.get("line")).strip(),
        },
        "reward": _safe_str(payload.get("reward")).strip(),
        "followup_hooks": _safe_list(payload.get("followup_hooks")),
    }


def _parse_llm_narration_payload(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw

    text = _safe_str(raw).strip()
    if not text:
        return {}

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"\s*```$", "", text).strip()

    parsed_json = _extract_json_object_from_text(text)
    if parsed_json:
        return parsed_json

    return parse_scene_response(text)


def _strict_narration_payload(value: Dict[str, Any]) -> Dict[str, Any]:
    value = _safe_dict(value)
    npc = _safe_dict(value.get("npc"))
    return {
        "format_version": "rpg_narration_v2",
        "narration": _safe_str(value.get("narration")).strip(),
        # IMPORTANT: never inject "You act." here.
        "action": _safe_str(value.get("action")).strip(),
        "npc": {
            "speaker": _safe_str(npc.get("speaker")).strip(),
            "line": _safe_str(npc.get("line")).strip(),
        },
        "reward": "",
        "followup_hooks": _safe_list(value.get("followup_hooks")),
    }


def _strip_basic_markdown(text: Any) -> str:
    text = _safe_str(text)
    if not text:
        return ""
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return " ".join(text.split()).strip()


def _recent_authoritative_facts(narration_context: Dict[str, Any]) -> List[str]:
    narration_context = _safe_dict(narration_context)
    facts = []
    for row in _safe_list(narration_context.get("recent_authoritative_facts")):
        text = _safe_str(row).strip()
        if text:
            facts.append(text)
    return facts


def _extract_continuity_price_facts(narration_context: Dict[str, Any]) -> List[str]:
    facts = _recent_authoritative_facts(narration_context)
    hits: List[str] = []
    for fact in facts:
        lower = fact.lower()
        if "room" in lower and ("gold" in lower or "silver" in lower or "copper" in lower):
            hits.append(fact)
    return hits


def _extract_present_actor_names(scene: Dict[str, Any], narration_context: Dict[str, Any]) -> List[str]:
    names: List[str] = []
    seen = set()

    def _add(value: Any) -> None:
        name = _safe_str(value).strip()
        if not name:
            return
        key = name.lower()
        if key in seen:
            return
        seen.add(key)
        names.append(name)

    for actor in _safe_list(_safe_dict(scene).get("actors")):
        if isinstance(actor, dict):
            _add(actor.get("name") or actor.get("id"))
        else:
            _add(actor)

    for actor in _safe_list(_safe_dict(narration_context.get("grounded")).get("present_actor_names")):
        _add(actor)

    resolved = _safe_dict(narration_context.get("resolved_result"))
    _add(resolved.get("target_name"))
    _add(resolved.get("npc_name"))
    _add(resolved.get("speaker_name"))
    _add(_safe_dict(resolved.get("npc")).get("name"))
    return names


def _extract_price_tokens(text: str) -> set:
    number_pattern = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
    return set(re.findall(rf"\b{number_pattern}\s*(gold|silver|copper)\b", text.lower()))


def _sanitize_narration_text(
    text: Any,
    scene: Dict[str, Any],
    narration_context: Dict[str, Any],
) -> str:
    text = _safe_str(text).strip()
    if not text:
        return ""

    allowed_names = {name.lower(): name for name in _extract_present_actor_names(scene, narration_context)}
    continuity_price_facts = _extract_continuity_price_facts(narration_context)

    banned_generic_terms = (
        "guard",
        "guards",
        "merchant guild",
        "guild",
        "town guard",
        "soldier",
        "soldiers",
    )

    IGNORE_NAMES = {
        "the tavern",
        "the room",
        "the inn",
        "the bar",
        "the rusty flagon tavern",
    }

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    kept: List[str] = []

    for sentence in sentences:
        lower = sentence.lower()

        # Reject raw JSON leakage or partial structured output.
        if sentence.startswith("{") or '"format_version"' in sentence or '"narration"' in sentence:
            continue

        # Reject invented off-scene enforcement / faction actors unless they are present.
        if any(term in lower for term in banned_generic_terms):
            # allow passive mentions, reject active invention
            if not re.search(r"\b(call|calls|called|signal|signals|signaled|summon|summons|summoned|order|orders|ordered|arrive|arrives|arrived|rush|rushes|rushed|draw|draws|drew|attack|attacks|attacked|spread|spreads|spreads)\b", lower):
                kept.append(sentence)
                continue
            else:
                continue

        # If a recent authoritative room price exists, reject contradictory new price narration.
        if continuity_price_facts and "room" in lower and ("gold" in lower or "silver" in lower or "copper" in lower):
            prior_price_tokens = set()
            for fact in continuity_price_facts:
                prior_price_tokens.update(_extract_price_tokens(fact))
            current_price_tokens = _extract_price_tokens(sentence)
            if current_price_tokens and not current_price_tokens.issubset(prior_price_tokens):
                continue

        # Reject named actor mentions that are not present/grounded.
        candidate_names = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\b", sentence)
        unknown_name = False
        for raw_name in candidate_names:
            key = raw_name.strip().lower()
            if key in IGNORE_NAMES:
                continue
            if key not in allowed_names:
                unknown_name = True
                break
        if unknown_name:
            continue

        kept.append(sentence)

    if not kept:
        # fallback to authoritative action
        turn_contract = _safe_dict(narration_context.get("turn_contract"))
        narration_brief = _safe_dict(turn_contract.get("narration_brief"))
        resolved = _safe_dict(narration_context.get("resolved_result"))
        fallback = _safe_str(
            narration_brief.get("summary")
            or resolved.get("narrative_brief")
            or resolved.get("message")
            or resolved.get("summary")
            or _authoritative_action_text(narration_context)
        )
        if fallback.strip().lower() in {"action: you act.", "you act.", "action: you act"}:
            fallback = "The action changes the scene, and the people nearby react according to what just happened."
        return _bound_text(fallback, 220)

    return _bound_text(" ".join(kept), 1400)


def _authoritative_action_text(narration_context: Dict[str, Any]) -> str:
    text = _strip_basic_markdown(_build_action_result_line(narration_context)).strip()
    text = re.sub(r"^(?:\*\*)?action(?:\*\*)?\s*:\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def _authoritative_reward_text(narration_context: Dict[str, Any]) -> str:
    return _strip_basic_markdown(_build_rewards_block(narration_context))


def _allowed_npc_speakers(scene: Dict[str, Any], narration_context: Dict[str, Any]) -> List[str]:
    return _extract_present_actor_names(scene, narration_context)


def _sanitize_npc_block(
    payload: Dict[str, Any],
    scene: Dict[str, Any],
    narration_context: Dict[str, Any],
) -> Dict[str, str]:
    payload = _normalize_narration_json(payload)
    npc = _safe_dict(payload.get("npc"))
    speaker = _safe_str(npc.get("speaker")).strip()
    line = _safe_str(npc.get("line")).strip()

    if not line:
        return {"speaker": "", "line": ""}

    allowed = _allowed_npc_speakers(scene, narration_context)
    allowed_lut = {name.lower(): name for name in allowed}
    resolved = _safe_dict(_safe_dict(narration_context).get("resolved_result"))

    # Prefer authoritative target speaker if present.
    preferred = _first_nonempty(
        resolved.get("target_name"),
        resolved.get("npc_name"),
        resolved.get("speaker_name"),
        _safe_dict(resolved.get("npc")).get("name"),
    )

    if speaker:
        canonical = allowed_lut.get(speaker.lower())
        if canonical:
            speaker = canonical
        elif preferred and preferred.lower() in allowed_lut:
            speaker = allowed_lut.get(preferred.lower(), preferred)
        else:
            # Fall back to preferred authoritative speaker instead of dropping entirely
            if preferred and preferred.lower() in allowed_lut:
                speaker = allowed_lut.get(preferred.lower(), preferred)
            else:
                return {"speaker": "", "line": ""}
    elif preferred and preferred.lower() in allowed_lut:
        speaker = allowed_lut.get(preferred.lower(), preferred)

    line = _clean_npc_dialogue_line(line)
    if not line:
        return {"speaker": "", "line": ""}

    return {
        "speaker": speaker,
        "line": line,
    }


def _desystemify_text(text: str) -> str:
    text = _safe_str(text).strip()
    if not text:
        return ""

    banned_prefixes = (
        "The player ",
        "The NPC ",
        "The target ",
    )

    for prefix in banned_prefixes:
        if text.startswith(prefix):
            text = text.replace("The player ", "You ", 1)
            text = text.replace("The NPC ", "", 1)
            text = text.replace("The target ", "", 1)

    # normalize various internal id patterns
    text = text.replace("npc_bran", "Bran")
    text = text.replace("npc:0", "Bran")
    text = text.replace("np:bran", "Bran")
    text = text.replace("np:", "")
    text = text.replace("npc_", "")

    # grammar cleanup
    text = text.replace("You takes", "You take")
    text = text.replace("You attempts", "You attempt")
    text = text.replace("You tries", "You try")
    text = text.replace("You goes", "You go")
    text = text.replace("You is ", "You are ")
    text = text.replace("You was ", "You were ")

    text = text.replace(" asks player", " asks")

    return text


def _strip_meta_narration(text: str) -> str:
    text = _safe_str(text)

    forbidden_phrases = (
        "The player ",
        "The NPC ",
        "The target ",
        "Narrate ",
        "Interpret the action",
        "should react",
        "according to the state delta",
    )

    for phrase in forbidden_phrases:
        if phrase in text:
            return ""

    return text


def _fallback_in_world_narration(narration_context: Dict[str, Any]) -> str:
    turn_contract = _safe_dict(narration_context.get("turn_contract"))
    interpreted = _safe_dict(turn_contract.get("interpreted_action"))
    npc_behavior = _safe_dict(
        narration_context.get("npc_behavior_context")
        or turn_contract.get("npc_behavior_context")
    )

    intent = _safe_str(interpreted.get("intent")).lower()
    target_name = _safe_str(
        npc_behavior.get("target_name")
        or interpreted.get("target_name")
        or "Bran"
    )

    if intent == "service":
        return f"{target_name} looks you over from behind the bar, weighing your request before answering."
    if intent == "attack":
        return f"You move suddenly, turning the exchange violent. {target_name} recoils as the tavern around you goes tense."
    if intent == "apologize":
        return f"{target_name} watches you carefully, the apology landing against the memory of what just happened."
    if intent == "ask":
        return f"{target_name} studies you for a moment before answering, still shaped by the recent tension."

    return "The room shifts around your action, attention turning toward you as the moment changes."


def _enforce_npc_behavior(payload: Dict[str, Any], narration_context: Dict[str, Any]) -> Dict[str, Any]:
    turn_contract = _safe_dict(narration_context.get("turn_contract"))
    interpreted = _safe_dict(turn_contract.get("interpreted_action"))
    npc_behavior = _safe_dict(
        narration_context.get("npc_behavior_context")
        or turn_contract.get("npc_behavior_context")
    )

    target_id = _safe_str(interpreted.get("target_id"))
    target_name = _safe_str(
        npc_behavior.get("target_name")
        or interpreted.get("target_name")
        or target_id
    )

    if not (target_id and target_name):
        return payload

    npc = _safe_dict(payload.get("npc"))

    npc["speaker"] = target_name

    if not _safe_str(npc.get("line")):
        tone = _safe_str(npc_behavior.get("reaction_tone") or "wary")

        if tone == "hostile":
            npc["line"] = "You have made your point. Now get out before this gets worse."
        elif tone == "afraid":
            npc["line"] = "Stay back. I do not want any more trouble."
        elif tone == "friendly":
            npc["line"] = "All right, I am listening. What do you need?"
        else:
            npc["line"] = "Careful now. I am not sure what to make of you."

    # anti-repeat logic
    recent_lines = []
    for thread in _safe_list(narration_context.get("conversation_threads")):
        for recent in _safe_list(_safe_dict(thread).get("recent_lines")):
            recent_lines.append(_safe_str(_safe_dict(recent).get("text")).strip().lower())

    if any(_safe_str(npc.get("line")).strip().lower()[:40] in line for line in recent_lines):
        tone = _safe_str(npc_behavior.get("reaction_tone") or "wary")

        if tone == "hostile":
            npc["line"] = "I remember what you did. Choose your next words carefully."
        elif tone == "afraid":
            npc["line"] = "I am not forgetting that. Keep your distance."
        elif tone == "friendly":
            npc["line"] = "Go on, then. I am listening."
        else:
            npc["line"] = "Let us not pretend nothing happened."

    if npc.get("speaker") == "Player":
        npc["speaker"] = target_name

    payload["npc"] = npc
    return payload


def _sanitize_narration_payload(
    payload: Dict[str, Any],
    scene: Dict[str, Any],
    narration_context: Dict[str, Any],
    authoritative_action: str | None = None,
) -> Dict[str, Any]:
    payload = _normalize_narration_json(payload)

    if authoritative_action is None:
        authoritative_action = _authoritative_action_text(narration_context)
    authoritative_result_action = _authoritative_action_text(narration_context)
    authoritative_reward = _authoritative_reward_text(narration_context)
    sanitized_npc = _sanitize_npc_block(payload, scene, narration_context)

    if _safe_str(sanitized_npc.get("speaker")).lower() == "player":
        sanitized_npc["speaker"] = ""

    # Presentation-only narration text remains model-authored, but sanitized against hallucinations
    llm_narration = _safe_str(payload.get("narration")).strip()
    narration_text = _sanitize_narration_text(llm_narration, scene, narration_context)

    # Action and reward are authoritative-only.
    llm_action = _safe_str(payload.get("action")).strip()
    normalized = _normalize_narration_json({
        "format_version": NARRATION_JSON_FORMAT_VERSION,
        "narration": narration_text,
        "action": llm_action,
        "npc": sanitized_npc,
        "reward": _safe_str(payload.get("reward")).strip(),
        "followup_hooks": [],
    })

    reward_text = _desystemify_text(_safe_str(normalized.get("reward")))
    authoritative_reward = _authoritative_reward_text(narration_context)

    if reward_text and not authoritative_reward:
        reward_text = ""

    normalized["reward"] = reward_text

    normalized = _enforce_npc_behavior(normalized, narration_context)

    # Fallback: ensure physical reaction in narration if missing
    turn_contract = _safe_dict(narration_context.get("turn_contract"))
    interpreted = _safe_dict(turn_contract.get("interpreted_action"))
    npc_behavior = _safe_dict(
        narration_context.get("npc_behavior_context")
        or turn_contract.get("npc_behavior_context")
    )
    target_id = _safe_str(interpreted.get("target_id"))
    target_name = _safe_str(
        npc_behavior.get("target_name")
        or interpreted.get("target_name")
        or target_id
    )
    if target_id and target_name:
        narration = _safe_str(normalized.get("narrator") or normalized.get("narration")).strip()
        if target_name.lower() not in narration.lower():
            intent = _safe_str(interpreted.get("intent") or "").lower()
            if "attack" in intent:
                prefix = f"{target_name} recoils from the blow, the room going tense. "
            elif "apologize" in intent or "apology" in intent:
                prefix = f"{target_name} pauses, considering your words. "
            elif "ask" in intent:
                prefix = f"{target_name} turns toward you, attentive. "
            else:
                tone = _safe_str(npc_behavior.get("reaction_tone") or "wary")
                if tone == "hostile":
                    prefix = f"{target_name} snaps upright, anger flashing across their face. "
                elif tone == "afraid":
                    prefix = f"{target_name} recoils, instinctively putting space between you. "
                elif tone == "friendly":
                    prefix = f"{target_name} shifts, reacting to you with a hint of warmth. "
                else:
                    prefix = f"{target_name} stiffens, clearly affected by what just happened. "
            normalized["narration"] = prefix + narration

    narration_clean = _desystemify_text(_safe_str(normalized.get("narration")))
    narration_clean = _strip_meta_narration(narration_clean)

    service_result = _service_result_from_context(narration_context)
    grounded_narration = _service_grounded_narration_text(narration_context)
    if service_result.get("matched") and grounded_narration:
        narration_clean = grounded_narration

    if service_result.get("matched") and _service_narration_needs_grounding(narration_clean):
        grounded_narration = _service_grounded_narration_text(narration_context)
        if grounded_narration:
            narration_clean = grounded_narration

    if not narration_clean:
        # only fallback if LLM truly failed
        narration_clean = ""

    narration_clean = _strip_service_meta_language(narration_clean, narration_context)
    normalized["narration"] = narration_clean
    normalized["narration"] = _naturalize_service_debug_language(normalized["narration"])
    _sanitize_repeated_player_input_narration(normalized, narration_context)
    action_raw = _safe_str(normalized.get("action"))

    # Only strip CLEAR meta/system instructions
    if (
        "Narrate" in action_raw
        or "Interpret" in action_raw
        or "according to the state delta" in action_raw
    ):
        normalized["action"] = ""
    else:
        normalized["action"] = _desystemify_text(action_raw.strip())
        normalized["action"] = _ground_action_result_text(
            normalized["action"],
            narration_context,
        )
        if authoritative_result_action:
            normalized["action"] = authoritative_result_action
    normalized["action"] = _final_grounded_service_action_text(
        _safe_str(normalized.get("action")),
        narration_context,
    )
    normalized["narration"] = _naturalize_service_debug_language(
        _safe_str(normalized.get("narration"))
    )
    normalized["action"] = _naturalize_service_debug_language(
        _safe_str(normalized.get("action"))
    )
    npc = _safe_dict(normalized.get("npc"))
    if npc:
        npc["line"] = _naturalize_service_debug_language(_safe_str(npc.get("line")))
        normalized["npc"] = npc
    npc["speaker"] = _desystemify_text(_safe_str(npc.get("speaker")))
    npc["line"] = _clean_npc_dialogue_line(_desystemify_text(_safe_str(npc.get("line"))))

    service_result = _service_result_from_context(narration_context)
    service_purchase = _safe_dict(service_result.get("purchase"))
    service_application = _safe_dict(narration_context.get("service_application"))
    service_status = _safe_str(service_result.get("status"))
    blocked_reason = _safe_str(
        service_application.get("blocked_reason")
        or service_purchase.get("blocked_reason")
    )
    service_purchase_applied = (
        _safe_str(service_result.get("kind")) == "service_purchase"
        and (
            service_status == "purchased"
            or bool(service_purchase.get("applied"))
            or bool(service_application.get("applied"))
        )
    )
    service_purchase_offer_not_found = (
        _safe_str(service_result.get("kind")) == "service_purchase"
        and (
            service_status == "purchase_offer_not_found"
            or blocked_reason == "offer_not_found"
        )
    )

    if not service_result.get("matched"):
        continuity_price_facts = _extract_continuity_price_facts(narration_context)
        npc_lower = _safe_str(npc.get("line")).lower()
        if continuity_price_facts and ("gold" in npc_lower or "silver" in npc_lower or "copper" in npc_lower):
            prior_price_tokens = set()
            for fact in continuity_price_facts:
                prior_price_tokens.update(_extract_price_tokens(fact))
            current_price_tokens = _extract_price_tokens(npc["line"])
            if current_price_tokens and not current_price_tokens.issubset(prior_price_tokens):
                resolved_dialogue = _safe_str(_safe_dict(narration_context.get("resolved_result")).get("dialogue")).strip()
                npc["line"] = _clean_npc_dialogue_line(resolved_dialogue)

    preserve_backed_memory_reference = (
        _line_has_prior_memory_reference(npc["line"])
        and _memory_reference_is_backed(npc["line"], narration_context)
    )

    if (
        service_result.get("matched")
        and not preserve_backed_memory_reference
        and (
            service_status in {
                "offers_available",
                "no_registered_offers",
                "blocked",
                "purchased",
                "purchase_ready",
                "purchase_offer_not_found",
            }
            or service_purchase_applied
            or service_purchase_offer_not_found
            or _service_claim_needs_grounding(npc["line"])
        )
    ):
        grounded_line = _service_grounded_npc_line(narration_context)
        if grounded_line:
            npc["line"] = grounded_line
    else:
        npc["line"] = _ground_accommodation_npc_line(npc["line"], narration_context)

    npc["line"] = _strip_unbacked_memory_reference_from_npc_line(
        npc["line"],
        narration_context,
    )

    normalized["npc"] = npc

    if not _safe_str(_safe_dict(normalized.get("npc")).get("line")):
        original_npc = _safe_dict(payload.get("npc"))
        if _safe_str(original_npc.get("line")):
            npc = _safe_dict(normalized.get("npc"))
            npc["speaker"] = _safe_str(npc.get("speaker") or original_npc.get("speaker")).strip()
            restored_line = _clean_npc_dialogue_line(original_npc.get("line"))
            service_result = _service_result_from_context(narration_context)
            if service_result.get("matched") and _service_claim_needs_grounding(restored_line):
                restored_line = _service_grounded_npc_line(narration_context)
            else:
                restored_line = _ground_accommodation_npc_line(restored_line, narration_context)
            restored_line = _strip_unbacked_memory_reference_from_npc_line(
                restored_line,
                narration_context,
            )
            npc["line"] = restored_line
            normalized["npc"] = npc

    travel_narration = _grounded_travel_narration(narration_context)
    travel_action = _grounded_travel_action(narration_context)
    if travel_narration:
        normalized["narration"] = travel_narration
    if travel_action:
        normalized["action"] = travel_action

    _apply_grounded_conversation_beat(normalized, narration_context)
    conversation = _conversation_result_from_context(narration_context)
    if conversation.get("triggered"):
        normalized["action"] = "Ambient conversation continues nearby."
        if not _safe_str(normalized.get("narration")) or "success" in _safe_str(normalized.get("narration")).lower():
            normalized["narration"] = "Nearby voices continue in the living world around you."

    return normalized


def _render_narration_text_from_json(payload: Dict[str, Any]) -> str:
    payload = _normalize_narration_json(payload)
    parts: List[str] = []

    if payload["narration"]:
        parts.append(payload["narration"])

    if payload["action"]:
        parts.append(payload["action"])

    npc = _safe_dict(payload.get("npc"))
    speaker = _safe_str(npc.get("speaker")).strip()
    line = _safe_str(npc.get("line")).strip()
    if speaker and line:
        parts.append(f'{speaker}: "{line}"')
    elif line:
        parts.append(line)

    if payload["reward"]:
        parts.append(f"Rewards: {payload['reward']}")

    return "\n\n".join([p for p in parts if p]).strip()


def _recover_narration_from_raw_text(text: str) -> Dict[str, Any]:
    text = _safe_str(text).strip()
    if not text:
        return _normalize_narration_json({})

    if text.startswith("{") or '"format_version"' in text or '"narration"' in text:
        extracted = _extract_json_object_from_text(text)
        if extracted:
            return _normalize_narration_json(extracted)
        return _normalize_narration_json({})

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    narration_parts: List[str] = []
    action_parts: List[str] = []
    npc_speaker = ""
    npc_line = ""
    reward = ""

    for line in lines:
        lower = line.lower()
        if lower.startswith("narrator:"):
            narration_parts.append(line.split(":", 1)[1].strip())
        elif lower.startswith("action:"):
            action_parts.append(line.split(":", 1)[1].strip())
        elif lower.startswith("npc:"):
            rest = line.split(":", 1)[1].strip()
            if ":" in rest:
                maybe_speaker, maybe_line = rest.split(":", 1)
                npc_speaker = maybe_speaker.strip()
                npc_line = maybe_line.strip().strip('"')
            else:
                npc_line = rest.strip().strip('"')
        elif lower.startswith("reward:"):
            reward = line.split(":", 1)[1].strip()
        else:
            narration_parts.append(line)

    return _normalize_narration_json({
        "format_version": NARRATION_JSON_FORMAT_VERSION,
        "narration": " ".join(narration_parts).strip(),
        "action": " ".join(action_parts).strip(),
        "npc": {
            "speaker": npc_speaker,
            "line": npc_line,
        },
        "reward": reward,
        "followup_hooks": [],
    })


def _structured_fallback_response() -> str:
    return (
        "NARRATOR: [ERROR: LLM FORMAT INVALID]\n"
        "ACTION: [NO VALID RESPONSE]\n"
    )


def _build_scene_summary(scene: Dict[str, Any], llm_narrative: str) -> str:
    scene = _safe_dict(scene)
    title = _safe_str(scene.get("title")).strip()
    location_name = _first_nonempty(
        scene.get("location_name"),
        scene.get("location_id"),
        scene.get("scene_id"),
    )
    summary = _safe_str(scene.get("summary")).strip()

    if summary:
        if title:
            return f"You are in {title}. {summary}"
        return summary

    llm_lines = _extract_text_lines(llm_narrative)
    if llm_lines:
        return llm_lines[0]

    if title and location_name:
        return f"You are in {title} at {location_name}."
    if title:
        return f"You are in {title}."
    if location_name:
        return f"You are at {location_name}."
    return "The scene settles around you."


def _build_combat_facts_block(narration_context: Dict[str, Any]) -> str:
    combat_result = _safe_dict(narration_context.get("combat_result"))
    npc_combat_result = _safe_dict(narration_context.get("npc_combat_result"))
    combat_state = _safe_dict(narration_context.get("combat_state"))
    if not combat_result and not combat_state and not npc_combat_result:
        return "- none"

    parts = []
    if combat_state:
        parts.append(f'state={_safe_str(combat_state.get("phase") or "idle")}')
    if combat_result:
        parts.append(f'hit={bool(combat_result.get("hit"))}')
        parts.append(f'damage={int(combat_result.get("damage_total", 0) or 0)}')
        parts.append(f'target_downed={bool(combat_result.get("target_downed"))}')
    if npc_combat_result:
        parts.append(f'npc_counterattack_hit={bool(npc_combat_result.get("hit"))}')
        parts.append(f'npc_counterattack_damage={int(npc_combat_result.get("damage_total", 0) or 0)}')
    return ", ".join(parts) if parts else "- none"


def _build_action_result_line(narration_context: Dict[str, Any]) -> str:
    narration_context = _safe_dict(narration_context)
    combat_result = _safe_dict(narration_context.get("combat_result"))
    if combat_result:
        hit = bool(combat_result.get("hit"))
        damage_total = int(combat_result.get("damage_total", 0) or 0)
        target_downed = bool(combat_result.get("target_downed"))
        target_name = _safe_str(combat_result.get("target_name") or _safe_dict(narration_context.get("resolved_result")).get("target_name")).strip() or "the target"
        if not hit:
            return f"You miss {target_name}."
        if target_downed:
            return f"You strike {target_name}, dealing {damage_total} damage and knocking them down."
        return f"You hit {target_name}, dealing {damage_total} damage."

    resolved = _safe_dict(narration_context.get("resolved_result"))
    service_result = _service_result_from_context(narration_context)
    if service_result.get("matched"):
        grounded_service_action = _service_grounded_action_result(narration_context)
        if grounded_service_action:
            return grounded_service_action

    combat = _safe_dict(resolved.get("combat_result"))
    action_type = _safe_str(narration_context.get("action_type")).strip()
    action_label = _titleize_action(action_type)

    outcome = _safe_str(combat.get("outcome")).strip().lower()
    target_name = _first_nonempty(
        combat.get("target_name"),
        resolved.get("target_name"),
        resolved.get("npc_name"),
        resolved.get("target_id"),
    )
    damage = int(combat.get("damage", resolved.get("damage", 0)) or 0)

    if outcome in ("hit", "crit", "graze", "miss"):
        if outcome == "miss":
            if target_name:
                return f"**{action_label}:** You miss **{target_name}**."
            return f"**{action_label}:** You miss."
        if target_name:
            return f"**{action_label}:** {outcome.title()} on **{target_name}** for **{damage} damage**."
        return f"**{action_label}:** {outcome.title()} for **{damage} damage**."

    if resolved.get("ok") is False:
        message = _first_nonempty(resolved.get("message"), resolved.get("reason"))
        if message:
            return f"**{action_label}:** {message}"
        return f"**{action_label}:** The attempt fails."

    message = _first_nonempty(
        resolved.get("message"),
        resolved.get("summary"),
        resolved.get("result_text"),
    )
    if message:
        return f"**{action_label}:** {message}"

    return ""


def _pick_npc_reply_text(llm_narrative: str) -> str:
    """Extract NPC dialogue from LLM narrative text."""
    # Look for quoted text or dialogue patterns
    import re
    quotes = re.findall(r'"([^"]*)"', _safe_str(llm_narrative))
    if quotes:
        return quotes[0]
    # Look for dialogue after colons
    dialogue_match = re.search(r':\s*([^.!?]+[.!?])', _safe_str(llm_narrative))
    if dialogue_match:
        return dialogue_match.group(1).strip()
    return ""


def _build_npc_reply_block(scene: Dict[str, Any], narration_context: Dict[str, Any], llm_narrative: str) -> str:
    narration_context = _safe_dict(narration_context)
    resolved = _safe_dict(narration_context.get("resolved_result"))

    reply = _first_nonempty(
        resolved.get("npc_reply"),
        resolved.get("reply"),
        resolved.get("dialogue"),
        resolved.get("spoken_response"),
    )
    if reply:
        return reply

    target_name = _first_nonempty(
        resolved.get("target_name"),
        resolved.get("npc_name"),
        resolved.get("target_id"),
    )
    picked = _pick_npc_reply_text(llm_narrative)
    if picked:
        if target_name and target_name.lower() not in picked.lower():
            return f"**{target_name}:** {picked}"
        return picked
    return ""


def _build_rewards_block(narration_context: Dict[str, Any]) -> str:
    narration_context = _safe_dict(narration_context)
    xp_result = _safe_dict(narration_context.get("xp_result"))
    skill_xp_result = _safe_dict(narration_context.get("skill_xp_result"))
    level_up = _safe_list(narration_context.get("level_up"))
    skill_level_ups = _safe_list(narration_context.get("skill_level_ups"))
    resolved = _safe_dict(narration_context.get("resolved_result"))

    parts: List[str] = []

    player_xp = int(xp_result.get("player_xp", 0) or 0)
    if player_xp > 0:
        parts.append(f"**+{player_xp} XP**")

    awards = _safe_dict(skill_xp_result.get("awards"))
    skill_parts = []
    for skill_id in sorted(awards.keys()):
        amount = int(awards.get(skill_id, 0) or 0)
        if amount > 0:
            skill_parts.append(f"**+{amount} {skill_id} XP**")
    if skill_parts:
        parts.append(", ".join(skill_parts))

    item_name = _first_nonempty(
        resolved.get("item_name"),
        _safe_dict(resolved.get("dropped_item")).get("name"),
        _safe_dict(resolved.get("picked_up_item")).get("name"),
        _safe_dict(resolved.get("item")).get("name"),
    )
    if item_name:
        parts.append(f"**Item:** {item_name}")

    if level_up:
        parts.append("**Level Up!**")

    if skill_level_ups:
        labels = []
        for entry in skill_level_ups:
            entry = _safe_dict(entry)
            skill_id = _first_nonempty(entry.get("skill_id"), entry.get("name"))
            if skill_id:
                labels.append(skill_id)
        if labels:
            parts.append("**Skill Up:** " + ", ".join(labels))

    return " · ".join(parts)


def _collect_emphasis_markers(scene: Dict[str, Any], narration_context: Dict[str, Any], blocks: Dict[str, str]) -> List[str]:
    scene = _safe_dict(scene)
    narration_context = _safe_dict(narration_context)
    resolved = _safe_dict(narration_context.get("resolved_result"))
    xp_result = _safe_dict(narration_context.get("xp_result"))
    markers: List[str] = []

    for value in [
        scene.get("title"),
        scene.get("location_name"),
        resolved.get("target_name"),
        resolved.get("npc_name"),
        _safe_dict(resolved.get("item")).get("name"),
        _safe_dict(resolved.get("picked_up_item")).get("name"),
        _safe_dict(resolved.get("dropped_item")).get("name"),
    ]:
        text = _safe_str(value).strip()
        if text:
            markers.append(text)

    damage = int(_safe_dict(resolved.get("combat_result")).get("damage", resolved.get("damage", 0)) or 0)
    if damage > 0:
        markers.append(f"{damage} damage")

    player_xp = int(xp_result.get("player_xp", 0) or 0)
    if player_xp > 0:
        markers.append(f"+{player_xp} XP")

    if _safe_list(narration_context.get("level_up")):
        markers.append("Level Up!")

    deduped: List[str] = []
    seen = set()
    for marker in markers:
        key = marker.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(marker)
    return deduped


def apply_narration_emphasis(text: str, emphasis_markers: List[str]) -> str:
    rendered = _safe_str(text)
    for marker in sorted(_safe_list(emphasis_markers), key=len, reverse=True):
        marker = _safe_str(marker).strip()
        if not marker:
            continue
        # Only match standalone text (avoid breaking markdown or double wrapping)
        pattern = rf"(?<!\*)\b{re.escape(marker)}\b(?!\*)"
        rendered = re.sub(pattern, f"**{marker}**", rendered)
    rendered = rendered.replace("****", "**")
    return rendered


def build_structured_narration(scene: Dict[str, Any], narration_context: Dict[str, Any], llm_narrative: str) -> Dict[str, Any]:
    parsed = _with_scene_response_defaults(parse_scene_response(llm_narrative))
    npc = _normalize_speaker_block(parsed.get("npc"))
    npc_text = npc.get("text", "")
    action_text = _safe_str(parsed.get("action")).strip() or _build_action_result_line(narration_context)
    rewards_text = _build_rewards_block(narration_context)
    speaker_turns = _build_speaker_turns(parsed)

    blocks = {
        "scene_summary": parsed["narrator"],
        "action_result_line": action_text,
        "npc_reply_block": npc_text,
        "rewards_block": rewards_text,
    }
    emphasis_markers = _collect_emphasis_markers(scene, narration_context, blocks)

    ordered = [
        parsed["narrator"],
        f"**Action:** {action_text}" if action_text else "",
        (
            f"**Reply:** {npc['name'] or 'Character'}: {npc['text']}"
            if npc.get("text")
            else ""
        ),
        f"**Reward:** {rewards_text}" if rewards_text else "",
    ]
    markdown = "\n\n".join(filter(None, ordered))
    markdown = apply_narration_emphasis(markdown, emphasis_markers)

    if len(markdown) > _NARRATION_MAX_MARKDOWN:
        cutoff = markdown[:_NARRATION_MAX_MARKDOWN]
        last_break = cutoff.rfind("\n")
        if last_break > 0:
            cutoff = cutoff[:last_break]
        markdown = cutoff.rstrip() + "..."

    return {
        "scene_summary": apply_narration_emphasis(parsed["narrator"], emphasis_markers),
        "action_result_line": apply_narration_emphasis(action_text, emphasis_markers),
        "npc_reply_block": apply_narration_emphasis(npc_text, emphasis_markers),
        "npc": {
            **npc,
            "text": apply_narration_emphasis(npc_text, emphasis_markers),
        },
        "rewards_block": apply_narration_emphasis(rewards_text, emphasis_markers),
        "emphasis_markers": emphasis_markers,
        "speaker_turns": speaker_turns,
        "markdown": markdown,
    }


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class NPCReaction:
    """An NPC's reaction to a scene event."""
    npc_id: str = ""
    npc_name: str = ""
    reaction: str = ""
    dialogue: str = ""
    emotion: str = "neutral"
    intent: str = ""


@dataclass
class NarrativeResult:
    """Complete result from scene narration."""
    narrative: str
    choices: List[Dict[str, Any]] = field(default_factory=list)
    npc_reactions: List[NPCReaction] = field(default_factory=list)
    dialogue_blocks: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _normalize_response_length(value: Any) -> str:
    value = str(value or "").strip().lower()
    if value in ("short", "medium", "long"):
        return value
    return "short"


def _response_length_prompt_rules(response_length: str) -> str:
    response_length = _normalize_response_length(response_length)

    if response_length == "long":
        return (
            "NARRATOR: 5 to 7 sentences describing the scene.\n"
            "ACTION: 5 to 7 sentences describing the result of the player's action.\n"
            "NPC: <npc_name>: \"no restrictions on length\" (omit if none)\n"
            "REWARD: <xp/items if any, else omit>"
        )

    if response_length == "medium":
        return (
            "NARRATOR: 3 to 5 sentences describing the scene.\n"
            "ACTION: 3 to 5 sentences describing the result of the player's action.\n"
            "NPC: <npc_name>: \"3 to 5 short sentences\" (omit if none)\n"
            "REWARD: <xp/items if any, else omit>"
        )

    return (
        "NARRATOR: 2 to 3 short sentence describing the scene.\n"
        "ACTION: 2 to 3 short sentence describing the result of the player's action.\n"
        "NPC: <npc_name>: \"2 - 3 short reply\" (omit if none)\n"
        "REWARD: <xp/items if any, else omit>"
    )


def build_scene_prompt(scene, narration_context, tone="dramatic"):
    """Build an LLM prompt to narrate a scene with strict structured output format.

    Returns:
        Prompt string for the LLM.
    """
    # ✅ Apply scene grounding FIRST before any prompt construction
    from app.rpg.session.runtime import (
        _apply_grounded_scene_overlay,
        _derive_grounded_scene_context,
        _normalize_prompt_location_name,
    )
    simulation_state = narration_context.get("simulation_state") or {}
    runtime_state = narration_context.get("runtime_state") or {}
    turn_result = narration_context.get("resolved_result") or {}
    
    grounded = _derive_grounded_scene_context(simulation_state, runtime_state, turn_result)
    scene = _apply_grounded_scene_overlay(scene, grounded)
    
    # ✅ Get final values from authoritative grounded state
    title = _safe_str(scene.get("title") or grounded.get("scene_title")).strip() or "Current Scene"
    summary = _safe_str(scene.get("summary") or grounded.get("scene_summary")).strip()
    
    # ✅ Normalize actors: convert dicts to names, always have safe fallback
    raw_actors = _safe_list(scene.get("actors") or grounded.get("present_actor_names"))
    actors = []
    for a in raw_actors:
        if isinstance(a, dict):
            actors.append(_safe_str(a.get("name") or a.get("id") or "Unknown"))
        else:
            actors.append(_safe_str(a))
    
    # ✅ Hard fallback: Actors present is never empty
    if not actors:
        actors = ["Other people nearby"]
    
    raw_location = _safe_str(scene.get("location_name") or turn_result.get("location_name")).strip()
    location = _normalize_prompt_location_name(raw_location, _safe_str(grounded.get("location_name"))) or "Current Location"
    stakes = scene.get("stakes", "much is at stake")
    tension = scene.get("tension", "moderate")

    actor_list = ""
    if actors:
        if isinstance(actors, list):
            actor_list = "\n".join(f"  - {a}" for a in actors)
        elif isinstance(actors, dict):
            actor_list = "\n".join(f"  - {k}: {v}" for k, v in actors.items())
        else:
            actor_list = str(actors)

    safe_context = _build_safe_prompt_context(scene, narration_context)
    
    # Build conversation threads context
    conversation_threads = _safe_list(narration_context.get("conversation_threads"))
    conversation_threads_block = ""
    if conversation_threads:
        lines = ["ONGOING CONVERSATION THREADS:"]
        for thread in conversation_threads[:4]:
            thread = _safe_dict(thread)
            topic = _safe_dict(thread.get("topic"))
            lines.append(
                f"- {_safe_str(thread.get('thread_id'))} | participants={', '.join(_safe_str(p) for p in _safe_list(thread.get('participants'))[:6])} | topic={_safe_str(topic.get('summary'))[:240]}"
            )
            for line in _safe_list(thread.get("recent_lines"))[-4:]:
                line = _safe_dict(line)
                lines.append(
                    f"  {_safe_str(line.get('speaker_name') or line.get('speaker_id'))}: {_safe_str(line.get('text'))[:220]}"
                )
        conversation_threads_block = "\n".join(lines)
    else:
        conversation_threads_block = "none"
    
    recent_authoritative_facts = _recent_authoritative_facts(narration_context)
    recent_facts_block = "\n".join(f"- {fact}" for fact in recent_authoritative_facts[:3]) or "- none"
    combat_facts_block = _build_combat_facts_block(narration_context)

    schema = """
Use exactly this object shape:
{
  "format_version": "rpg_narration_v2",
  "narration": "<descriptive scene narration grounded in turn_contract>",
  "action": "<short, in-world description of what happened (1–2 sentences, no meta language)>",
  "npc": {
    "speaker": "<target NPC name if the interpreted action targets an NPC, otherwise empty string>",
    "line": "<natural in-character dialogue matching npc_behavior_context.reaction_tone, or empty string only if no NPC reaction is needed>"
  },
  "reward": "<reward summary or empty string>",
  "followup_hooks": []
}
"""

    prompt = f"""You are a deterministic RPG narration engine.

CONTEXT:
{safe_context}

Recent authoritative facts:
{recent_facts_block}

Authoritative combat facts:
{combat_facts_block}

Turn contract PRIMARY TRUTH:
{json.dumps(_safe_dict(narration_context.get("turn_contract")), ensure_ascii=False, indent=2)[:6000]}

NPC STATE SUMMARY (must influence tone and dialogue):
{json.dumps({
    "mood": _safe_dict(narration_context.get("npc_behavior_context") or _safe_dict(narration_context.get("turn_contract")).get("npc_behavior_context")).get("mood"),
    "relationship": _safe_dict(narration_context.get("npc_behavior_context") or _safe_dict(narration_context.get("turn_contract")).get("npc_behavior_context")).get("relationship_to_player"),
    "trust": _safe_dict(narration_context.get("npc_behavior_context") or _safe_dict(narration_context.get("turn_contract")).get("npc_behavior_context")).get("trust"),
    "fear": _safe_dict(narration_context.get("npc_behavior_context") or _safe_dict(narration_context.get("turn_contract")).get("npc_behavior_context")).get("fear"),
    "recent_memories": _safe_list(_safe_dict(narration_context.get("npc_behavior_context") or _safe_dict(narration_context.get("turn_contract")).get("npc_behavior_context")).get("recent_memories"))
}, ensure_ascii=False)}

NPC behavior context:
{json.dumps(_safe_dict(narration_context.get("npc_behavior_context") or _safe_dict(narration_context.get("turn_contract")).get("npc_behavior_context")), ensure_ascii=False, indent=2)[:3000]}

Ongoing conversation threads:
{conversation_threads_block}

YOUR ONLY TASK: Generate narration for a player's action in an RPG.

OUTPUT ONLY VALID JSON.
Do not include markdown fences.
Do not include commentary outside JSON.
{schema}

 IMPORTANT RULES:
 - Output ONLY valid JSON with no extra text
 - NO markdown fences or commentary outside the JSON object
 - NO content about ticks, time, or system messages
 - NO faction goals, loyalty, awareness, or ambient content
TURN CONTRACT RULES:
- turn_contract is the primary truth for this turn.
- resolved_result is legacy compatibility; prefer turn_contract when both are present.
- You MUST base the narration primarily on turn_contract.narration_brief.
- You MUST reflect turn_contract.state_delta when it exists.
- You MUST NOT invent state changes outside turn_contract.state_delta, resolved_result, or combat facts.
- You may freely add sensory detail, body language, pacing, and natural dialogue as presentation only.
- NEVER copy or restate narration_brief directly. Convert it into in-world description.
- NEVER refer to "the player" in narration. Always describe actions in-world (e.g., "You step forward..." or omit subject).
- NEVER output internal IDs like npc:0, npc_bran, player, target_id, action_type, state_delta, narration_brief, or turn_contract.
- The final prose must sound like an RPG narrator, not a debug summary.
- If your output resembles an instruction, rewrite it into a natural in-world description.
- If narration sounds like a system description, rewrite it before finalizing.
- Never output generic filler like "Action: You act."

NPC REACTION RULES:
- If turn_contract.interpreted_action.target_id exists, that NPC MUST visibly react.
- If npc_behavior_context.required_reaction is true, include either:
  1. physical/body-language reaction, or
  2. direct dialogue, preferably both.
- NPC dialogue must match npc_behavior_context.reaction_tone.
- hostile/angry NPCs should not respond as friendly.
- wary NPCs should remain cautious even after an apology.
- recent_memories MUST influence tone and dialogue.
- If a memory includes violence or betrayal, NPC should reference or emotionally reflect it.
- If the player recently harmed an NPC, that NPC should remember it and respond accordingly.
- NPC dialogue should sound natural, not like a summary of emotions.
- Avoid phrases like "I am wary" or "I feel cautious".
- Express emotion through tone, word choice, and implication.
- Any combat description MUST match the authoritative combat facts block
- Do NOT invent hits, misses, damage, knockdowns, or combatants
- The reward field MUST stay empty unless the authoritative context explicitly shows XP, item, or level gain
- Do NOT invent gold, reputation, items, guards, factions, or bystanders not present in the scene/context
- NPC speaker MUST be one present actor or the explicit target NPC from context
- Keep continuity with the recent authoritative facts block below
- Do NOT change previously established prices, speakers, outcomes, or conflict state unless the current resolved result changed them
- Do not end the response with an ellipsis
- Finish with complete sentences
- Do not leave dialogue, action, or scene description trailing mid-thought

Conversation thread rules:
- If conversation_threads are provided, treat them as ongoing local dialogue context.
- Do not restart the same NPC line from scratch.
- Continue from recent_lines when the player's input references an ongoing exchange.
- NPCs may answer, pivot, interrupt, or defer, but must not invent rewards, inventory, combat results, locations, or new NPCs.
- If a thread has world_signals, phrase them as rumors, tension, suspicions, or social shifts only.
- Do not resolve or mutate authoritative state unless action_result already says it happened.

Relevant NPC memories from deterministic simulation:
{_format_recalled_service_memories_for_prompt(narration_context)}

Relevant general NPC memories:
{_format_recalled_npc_memories_for_prompt(narration_context)}

Deterministic NPC-to-NPC conversation beat:
{_format_conversation_beat_for_prompt(narration_context)}

Memory rules:
- NPCs may reference prior interactions only if they appear in Relevant NPC memories or Relevant general NPC memories.
- Do not invent prior purchases, debts, failed purchases, promises, favors, or relationships.
- If Relevant NPC memories is None, do not say "again", "last time", "remember", or imply a previous encounter.
- If a deterministic NPC-to-NPC conversation beat is provided, use only that speaker and line for the NPC dialogue. Do not invent additional conversation consequences.

SCENE:
Title: {title}
Location: {location}
Tone: {tone}
Tension: {tension}
Summary: {summary}
Actors present:
{actor_list}
Stakes: {stakes}

CONTEXT:
{safe_context}
"""
    logger.debug("[RPG PROMPT] Final prompt length: %d", len(prompt))
    return prompt


def build_npc_reaction_prompt(
    npc: Dict[str, Any],
    scene: Dict[str, Any],
    narrative: str,
    *,
    state: Optional[Dict[str, Any]] = None,
) -> str:
    """Build a prompt to generate an individual NPC reaction.

    Args:
        npc: NPC dict with name, personality, goals, memory, relationships, etc.
        scene: Current scene dict.
        narrative: The generated narrative text.
        state: Optional game state dict.

    Returns:
        Prompt string for the LLM.
    """
    npc_name = npc.get("name", "Unknown NPC")
    npc_personality = npc.get("personality", "")
    npc_goals = npc.get("goals", "")
    npc_relation = npc.get("relation_to_player", "neutral")
    scene_title = scene.get("title", "Unknown Scene")

    # Phase 5.1: Inject NPC state (memory, beliefs, relationships)
    # Phase 6: Enhanced with deterministic mind context
    npc_memory = npc.get("memory_summary", "")
    npc_beliefs = npc.get("beliefs", npc.get("belief_summary", {}))
    npc_relationships = npc.get("relationships", {})
    npc_active_goals = npc.get("active_goals", [])
    npc_last_decision = npc.get("last_decision", {})

    personality_info = f"Personality: {npc_personality}" if npc_personality else ""
    goals_info = f"Goals: {npc_goals}" if npc_goals else ""
    relation_info = f"Relation to player: {npc_relation}" if npc_relation else ""
    memory_info = f"Recent memory: {npc_memory}" if npc_memory else ""
    beliefs_info = f"Current beliefs: {', '.join(str(v) for v in npc_beliefs.values())}" if npc_beliefs else ""
    relationships_info = f"Relationships: {npc_relationships}" if npc_relationships else ""
    rumor_info = f"Rumors in circulation: {scene.get('active_rumors', [])}" if scene.get("active_rumors") else ""
    alliance_info = f"Active alliances: {scene.get('active_alliances', [])}" if scene.get("active_alliances") else ""
    faction_position_info = f"Faction positions: {scene.get('faction_positions', {})}" if scene.get("faction_positions") else ""
    # Phase 8.3: Add sandbox context to scene prompt
    sandbox_info = f"Sandbox summary: {scene.get('sandbox_summary', {})}" if scene.get("sandbox_summary") else ""
    world_consequence_info = f"Recent world consequences: {scene.get('world_consequences', [])}" if scene.get("world_consequences") else ""
    goals_list_info = f"Active goals: {npc_active_goals}" if npc_active_goals else ""
    last_decision_info = f"Last decision: {npc_last_decision}" if npc_last_decision else ""
    # Phase 7: Add debug context info for explainability
    debug_context_info = f"Scene debug context: {scene.get('debug_context', {})}" if scene.get("debug_context") else ""

    prompt = f"""You are generating NPC reactions for an RPG.

Character: {npc_name}
{personality_info}
{goals_info}
{relation_info}
{memory_info}
{beliefs_info}
{relationships_info}
{rumor_info}
{alliance_info}
    {faction_position_info}
    {sandbox_info}
    {world_consequence_info}
    {goals_list_info}
    {last_decision_info}
    {debug_context_info}

Scene: {scene_title}

Narrative:
{narrative[:1000]}

=== INSTRUCTIONS ===
Describe {npc_name}'s internal reaction to what just happened.
- Use the NPC's active goals to shape what they want right now.
- Use belief_summary about the player to determine tone.
- Use memory_summary to maintain continuity.
- Use last_decision so reactions align with recent intent.
- Do not contradict the provided structured state.
Then provide a short line of dialogue they might say.
Specify their emotional state (one of: calm, tense, angry, fearful, curious, excited, neutral).
Specify their immediate intent (one of: observe, act, confront, flee, negotiate, wait).

Respond ONLY in JSON format:
{{
  "reaction": "...",
  "dialogue": "...",
  "emotion": "...",
  "intent": "..."
}}
"""
    return prompt


def build_choice_prompt(
    scene: Dict[str, Any],
    narrative: str,
    *,
    num_choices: int = 3,
    action_hooks: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Build a prompt to generate player choices.

    Args:
        scene: Current scene dict.
        narrative: The narrative text.
        num_choices: Number of choices to generate.
        action_hooks: Optional list of action hooks from the scene.

    Returns:
        Prompt string for the LLM.
    """
    title = scene.get("title", "Scene")
    stakes = scene.get("stakes", "")
    source = scene.get("id", scene.get("source", ""))

    # Phase 5.1: Build action hooks for choice → action binding
    hooks_text = ""
    if action_hooks:
        hooks_text = "\nAvailable action types:\n"
        for hook in action_hooks:
            hooks_text += f"  - {hook.get('type', 'unknown')}: target={hook.get('target_id', source)}\n"
    else:
        # Default action hooks
        hooks_text = f"""
Available action types:
  - intervene_thread: target={source}
  - escalate_conflict: target={source}
  - observe_situation: target={source}
"""

    prompt = f"""You are generating player choices for an RPG scene.

Scene: {title}
Stakes: {stakes}
{hooks_text}
Narrative situation:
{narrative[-500:]}

=== INSTRUCTIONS ===
Generate exactly {num_choices} meaningful choices for the player.
Each choice should have:
  - A short, action-oriented description (5-10 words)
  - An implied risk or consequence
  - A distinct approach (combat, stealth, diplomacy, observation, etc.)
  - A mapped action type from the available action types above

Respond ONLY in JSON format:
{{
  "choices": [
    {{
      "text": "...",
      "type": "action|observe|dialogue|stealth|combat|diplomacy",
      "action": {{
        "type": "intervene_thread|escalate_conflict|observe_situation|...",
        "target_id": "..."
      }}
    }}
  ]
}}
"""
    return prompt


# ---------------------------------------------------------------------------
# Response parsers
# ---------------------------------------------------------------------------

def parse_scene_response(text: str) -> Dict[str, Any]:
    """Parse a raw LLM narrative response.

    Returns raw parsed fields only.
    Parses structured output format directly from LLM response.

    Handles both:
    - JSON format: {"format_version": "...", "narration": "...", "action": "...", ...}
    - Text format: NARRATOR: ...\nACTION: ...\nNPC: ...
    """
    logger.debug("[RPG PARSE] Starting to parse response, length: %d", len(text))

    result = {
        "narrator": "",
        "action": "",
        "npc": {
            "speaker_id": "",
            "name": "",
            "text": "",
            "emotion": "",
            "portrait": "",
        },
        "reward": "",
    }

    # Clean up the text
    text = _safe_str(text).strip()
    logger.debug("[RPG PARSE] Cleaned text: %r", text[:200] + "..." if len(text) > 200 else text)

    # Try JSON format first
    if text.startswith("{"):
        try:
            import json
            parsed_json = json.loads(text)
            if isinstance(parsed_json, dict):
                # Map JSON fields to result fields
                result["narrator"] = _safe_str(parsed_json.get("narration")).strip()
                result["action"] = _safe_str(parsed_json.get("action")).strip()

                npc = parsed_json.get("npc")
                if isinstance(npc, dict):
                    result["npc"] = {
                        "speaker_id": _safe_str(npc.get("speaker")).strip().replace(" ", "_").lower(),
                        "name": _safe_str(npc.get("speaker")).strip(),
                        "text": _bound_text(npc.get("line"), 180),
                        "emotion": "",
                        "portrait": "",
                    }

                result["reward"] = ""

                logger.debug("[RPG PARSE] Parsed JSON format: narrator=%r, action=%r, npc_text=%r",
                             result["narrator"][:50], result["action"][:50], result["npc"]["text"][:50])
                return result
        except Exception:
            logger.debug("[RPG PARSE] JSON parsing failed, falling back to text parsing")

    import re

    # Look for patterns anywhere in the text
    # NARRATOR pattern
    narrator_match = re.search(r'NARRATOR:\s*(.+?)(?=\n[A-Z]+:|\n*$)', text, re.DOTALL | re.IGNORECASE)
    if narrator_match:
        result["narrator"] = narrator_match.group(1).strip()
        logger.debug("[RPG PARSE] Found NARRATOR: %r", result["narrator"])

    # ACTION pattern
    action_match = re.search(r'ACTION:\s*(.+?)(?=\n[A-Z]+:|\n*$)', text, re.DOTALL | re.IGNORECASE)
    if action_match:
        result["action"] = action_match.group(1).strip()
        logger.debug("[RPG PARSE] Found ACTION: %r", result["action"])

    # NPC pattern
    npc_match = re.search(r'NPC:\s*(.+?)(?=\n[A-Z]+:|\n*$)', text, re.DOTALL | re.IGNORECASE)
    if npc_match:
        npc_text = npc_match.group(1).strip()
        logger.debug("[RPG PARSE] Found NPC text: %r", npc_text)
        if ":" in npc_text:
            name, text_part = npc_text.split(":", 1)
            npc_name = name.strip()
            result["npc"] = {
                "speaker_id": npc_name.lower().replace(" ", "_"),
                "name": npc_name,
                "text": _bound_text(text_part.strip().strip('"'), 180),
                "emotion": "",
                "portrait": "",
            }
            logger.debug("[RPG PARSE] Parsed NPC: name=%r, text=%r", npc_name, result["npc"]["text"])
        else:
            result["npc"] = {
                "speaker_id": "",
                "name": "",
                "text": _bound_text(npc_text, 180),
                "emotion": "",
                "portrait": "",
            }
            logger.debug("[RPG PARSE] Parsed NPC without name: text=%r", result["npc"]["text"])

    # REWARD pattern
    reward_match = re.search(r'REWARD:\s*(.+?)(?=\n[A-Z]+:|\n*$)', text, re.DOTALL | re.IGNORECASE)
    if reward_match:
        result["reward"] = _bound_text(reward_match.group(1).strip(), 120)
        logger.debug("[RPG PARSE] Found REWARD: %r", result["reward"])

    # Fallback: if no structured format found, try to extract from plain text
    if not result["narrator"] and not result["action"]:
        lines = text.split('\n')
        logger.debug("[RPG PARSE] No structured format found, using fallback with %d lines", len(lines))
        if lines:
            # Assume first line is narrator
            result["narrator"] = lines[0].strip()
            logger.debug("[RPG PARSE] Fallback NARRATOR: %r", result["narrator"])
        if len(lines) > 1:
            # Assume second line is action
            result["action"] = lines[1].strip()
            logger.debug("[RPG PARSE] Fallback ACTION: %r", result["action"])

    logger.debug("[RPG PARSE] Final parsed result: %s", result)
    return result


def _is_valid_scene_response(parsed: Dict[str, Any]) -> bool:
    parsed = _safe_dict(parsed)
    narrator = _safe_str(parsed.get("narrator")).strip()
    action = _safe_str(parsed.get("action")).strip()
    npc_text = _safe_str(parsed.get("npc", {}).get("text")).strip()

    blob = (narrator + "\n" + action + "\n" + npc_text).strip()
    if not blob:
        is_valid = False
    elif len(blob) <= 10:
        is_valid = False
    elif blob.startswith("{") or '"format_version"' in blob or '"narration"' in blob:
        # Do not treat leaked JSON / partial JSON as valid rendered prose.
        is_valid = False
    else:
        is_valid = True

    logger.warning("[RPG VALIDATE] narrator=%r, action=%r, npc_text=%r -> valid=%s",
                narrator[:50], action[:50], npc_text[:50], is_valid)
    return is_valid


def _with_scene_response_defaults(parsed: Dict[str, Any]) -> Dict[str, Any]:
    parsed = _safe_dict(parsed)

    npc = parsed.get("npc")
    if not isinstance(npc, dict):
        parsed["npc"] = {
            "speaker_id": "unknown",
            "name": "",
            "text": _safe_str(npc).strip(),
            "emotion": "",
            "portrait": "",
        }
    if not parsed.get("narrator"):
        parsed["narrator"] = "You are here."

    return parsed


def parse_npc_reaction(text: str, npc_id: str = "", npc_name: str = "") -> NPCReaction:
    """Parse an NPC reaction response.

    Phase 5.1: Attempts JSON parsing first, falls back to text extraction.

    Args:
        text: Raw LLM response for NPC reaction.
        npc_id: NPC identifier.
        npc_name: Fallback NPC name.

    Returns:
        NPCReaction dataclass instance.
    """
    # Phase 5.1: Try JSON parsing first
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return NPCReaction(
                npc_id=npc_id,
                npc_name=npc_name,
                reaction=data.get("reaction", ""),
                dialogue=data.get("dialogue", ""),
                emotion=data.get("emotion", "neutral").lower(),
                intent=data.get("intent", ""),
            )
    except (json.JSONDecodeError, TypeError):
        pass

    # Fallback: text extraction
    reaction = ""
    dialogue = ""
    emotion = "neutral"
    intent = ""

    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("REACTION:"):
            reaction = line[len("REACTION:"):].strip()
        elif line.startswith("DIALOGUE:"):
            dialogue = line[len("DIALOGUE:"):].strip().strip('"')
        elif line.startswith("EMOTION:"):
            emotion = line[len("EMOTION:"):].strip().lower()
        elif line.startswith("INTENT:"):
            intent = line[len("INTENT:"):].strip().lower()

    return NPCReaction(
        npc_id=npc_id,
        npc_name=npc_name,
        reaction=reaction,
        dialogue=dialogue,
        emotion=emotion,
        intent=intent,
    )


def parse_choices(text: str, source: str = "") -> List[Dict[str, Any]]:
    """Parse LLM-generated player choices.

    Phase 5.1: Attempts JSON parsing first, falls back to text extraction.
    Choices now include action binding for integration with apply_player_action.

    Args:
        text: Raw LLM response with numbered choices.
        source: Scene/source ID for action target binding.

    Returns:
        List of choice dicts with 'id', 'text', 'type', and 'action' keys.
    """
    # Phase 5.1: Try JSON parsing first
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "choices" in data:
            choices_data = data["choices"]
        elif isinstance(data, list):
            choices_data = data
        else:
            choices_data = []

        if choices_data:
            choices = []
            for i, c in enumerate(choices_data):
                if isinstance(c, dict):
                    action = c.get("action", {})
                    choices.append({
                        "id": f"choice_{i+1}",
                        "text": c.get("text", ""),
                        "type": c.get("type", "action"),
                        "action": {
                            "type": action.get("type", "intervene_thread"),
                            "target_id": action.get("target_id", source),
                        },
                    })
            if choices:
                return choices
    except (json.JSONDecodeError, TypeError):
        pass

    # Fallback: text extraction with default action binding
    choices = []
    choice_types = ["action", "observe", "dialogue", "stealth", "combat", "diplomacy"]
    action_types = ["intervene_thread", "observe_situation", "escalate_conflict"]

    for line in text.split("\n"):
        line = line.strip()
        if line and (line[0].isdigit() and line[1] in (".", ")")):
            choice_text = line[2:].strip()
            idx = len(choices) + 1
            choice_type = choice_types[idx % len(choice_types)]
            action_type = action_types[idx % len(action_types)]
            choices.append({
                "id": f"choice_{idx}",
                "text": choice_text,
                "type": choice_type,
                "action": {
                    "type": action_type,
                    "target_id": source,
                },
            })

    return choices if choices else [
        {"id": "choice_1", "text": "Take action", "type": "action", "action": {"type": "intervene_thread", "target_id": source}},
        {"id": "choice_2", "text": "Wait and observe", "type": "observe", "action": {"type": "observe_situation", "target_id": source}},
    ]


def apply_hooks_to_choices(
    choices: List[Dict[str, Any]],
    hooks: List[Dict[str, Any]],
    *,
    source: str = "",
) -> List[Dict[str, Any]]:
    """Inject action hooks into choices for binding.

    Phase 5.5: Maps scene action_hooks onto choice objects so that
    when a player selects a choice, the corresponding action is ready.

    Args:
        choices: List of choice dicts to update in-place.
        hooks: List of action hooks from the scene (e.g. from action_hooks).
        source: Fallback target_id when a hook has none.

    Returns:
        The same choices list, updated with action bindings.
    """
    for i, c in enumerate(choices):
        if i < len(hooks):
            hook = hooks[i]
            c["action"] = {
                "type": hook.get("type", "intervene_thread"),
                "target_id": hook.get("target_id", source),
            }
    return choices


# ---------------------------------------------------------------------------
# Scene narration service
# ---------------------------------------------------------------------------

class SceneNarrator:
    """Orchestrates scene narration with NPC reactions and player choices.

    This is the main entry point for Phase 5. It coordinates:
    1. Narrative generation from scene data
    2. NPC reaction generation
    3. Player choice generation
    4. Assembly into a complete NarrativeResult
    """

    def __init__(
        self,
        llm_gateway: Optional[Any] = None,
        *,
        default_tone: str = "dramatic",
        simulate_mode: bool = False,
    ):
        self.llm_gateway = llm_gateway
        self.default_tone = default_tone
        self.simulate_mode = simulate_mode
        self.live_mode = bool(llm_gateway) and not simulate_mode
        self._last_llm_success = False

    def narrate_scene(
        self,
        scene: Dict[str, Any],
        state: Dict[str, Any],
        *,
        tone: Optional[str] = None,
        include_npc_reactions: bool = True,
        include_choices: bool = True,
        max_npc_reactions: int = 3,
    ) -> NarrativeResult:
        """Generate a complete narrated scene.

        Args:
            scene: Scene dict to narrate.
            state: Current game state dict.
            tone: Override default tone.
            include_npc_reactions: Whether to generate NPC reactions.
            include_choices: Whether to generate player choices.
            max_npc_reactions: Max NPC reactions to generate.

        Returns:
            NarrativeResult with narrative, choices, and NPC reactions.
        """
        tone = tone or self.default_tone

        # Step 1: Generate narrative
        narrative = self._generate_narrative(scene, state, tone=tone)

        # Step 2: Generate NPC reactions
        npc_reactions: List[NPCReaction] = []
        if include_npc_reactions:
            npc_reactions = self._generate_npc_reactions(
                scene, narrative, state,
                max_reactions=max_npc_reactions,
            )

        # Step 3: Generate choices
        choices: List[Dict[str, Any]] = []
        if include_choices:
            choices = self._generate_choices(scene, narrative)

        # Step 4: Build dialogue blocks from NPC reactions
        dialogue_blocks = [
            {
                "speaker": r.npc_name,
                "npc_id": r.npc_id,
                "text": r.dialogue,
                "emotion": r.emotion,
            }
            for r in npc_reactions
            if r.dialogue
        ]

        # Phase 8: player-facing packaged view
        player_view = {
            "scene_id": scene.get("scene_id") or scene.get("id", ""),
            "scene_title": scene.get("title", ""),
            "mode": "scene",
            "active_npc_id": (
                npc_reactions[0].npc_id
                if npc_reactions
                else ""
            ),
            "encounter": build_encounter_view(scene, state),
            "active_rumors": list(scene.get("active_rumors") or [])[:3],
            "active_alliances": list(scene.get("active_alliances") or [])[:3],
            "faction_positions": dict(scene.get("faction_positions") or {}),
        }

        llm_success = getattr(self, "_last_llm_success", False)

        return NarrativeResult(
            narrative=narrative,
            choices=choices,
            npc_reactions=npc_reactions,
            dialogue_blocks=dialogue_blocks,
            metadata={
                "tone": tone,
                "scene_id": scene.get("id"),
                "npc_count": len(npc_reactions),
                "choice_count": len(choices),
                "llm_live": bool(self.live_mode and llm_success),
                "llm_attempted": bool(self.live_mode),
                "llm_fallback_used": not llm_success,
                "player_view": player_view,
                "sandbox_summary": scene.get("sandbox_summary", {}),
            },
        )

    def _generate_narrative(
        self,
        scene: Dict[str, Any],
        state: Dict[str, Any],
        tone: str,
    ) -> str:
        """Generate narrative text for a scene."""
        # Inject player_input from state into scene so simulation fallback sees it
        scene = dict(scene or {})
        if "player_input" not in scene and state:
            pi = state.get("player_input", "")
            if pi:
                scene["player_input"] = str(pi)

        if not self.live_mode:
            return self._simulate_narrative(scene, tone)

        try:
            prompt = build_scene_prompt(scene, state, tone=tone)
            response = _llm_text(self.llm_gateway, prompt, context={"scene": scene})
            parsed = parse_scene_response(response)
            narrative = parsed.get("narrative") or ""

            if narrative:
                self._last_llm_success = True
                return narrative
        except Exception:
            pass

        # fallback
        self._last_llm_success = False
        return self._simulate_narrative(scene, tone)

    def _generate_npc_reactions(
        self,
        scene: Dict[str, Any],
        narrative: str,
        state: Dict[str, Any],
        *,
        max_reactions: int = 3,
    ) -> List[NPCReaction]:
        """Generate NPC reactions for actors in the scene."""
        actors = scene.get("actors", [])
        if isinstance(actors, dict):
            actor_list = [{"id": k, "name": k, **v} for k, v in actors.items()]
        elif isinstance(actors, list):
            actor_list = [
                a if isinstance(a, dict) else {"id": a, "name": str(a)}
                for a in actors
            ]
        else:
            actor_list = [{"id": "unknown", "name": str(actors)}]

        reactions: List[NPCReaction] = []
        for actor in actor_list[:max_reactions]:
            npc_id = actor.get("id", "unknown")
            npc_name = actor.get("name", "Unknown")

            if not self.live_mode:
                reaction = self._simulate_npc_reaction(npc_name)
            else:
                try:
                    prompt = build_npc_reaction_prompt(actor, scene, narrative, state=state)
                    response = _llm_text(self.llm_gateway, prompt, context={"npc": npc_id})
                    reaction = parse_npc_reaction(response, npc_id=npc_id, npc_name=npc_name)
                    if reaction and reaction.reaction:
                        self._last_llm_success = True
                    else:
                        raise ValueError("empty reaction")
                except Exception:
                    self._last_llm_success = False
                    reaction = self._simulate_npc_reaction(npc_name)

            reactions.append(reaction)

        return reactions

    def _generate_choices(
        self,
        scene: Dict[str, Any],
        narrative: str,
    ) -> List[Dict[str, Any]]:
        """Generate player choices."""
        source = scene.get("id", scene.get("source", ""))
        action_hooks = scene.get("action_hooks", None)

        if not self.live_mode:
            return self._simulate_choices(scene, source)

        try:
            prompt = build_choice_prompt(scene, narrative, action_hooks=action_hooks)
            response = _llm_text(self.llm_gateway, prompt, context={"scene": scene.get("id")})
            parsed = parse_choices(response, source=source)
            if parsed:
                self._last_llm_success = True
                return parsed
        except Exception:
            pass

        self._last_llm_success = False
        return self._simulate_choices(scene, source)

    # ------------------------------------------------------------------
    # Simulation fallbacks (no LLM required)
    # ------------------------------------------------------------------

    @staticmethod
    def _simulate_narrative(scene: Dict[str, Any], tone: str) -> str:
        """Generate simulated narrative text without LLM.

        Incorporates player input and scene actors for varied responses.
        """
        title = scene.get("title", "The Scene")
        summary = scene.get("summary", "Events unfold around you.")
        stakes = scene.get("stakes", "much is at stake")
        player_input = scene.get("player_input", "")
        actors_data = scene.get("actors", [])

        # Extract NPC names from actor dicts
        npc_names = []
        if isinstance(actors_data, list):
            for a in actors_data[:5]:
                if isinstance(a, dict):
                    name = a.get("name", a.get("id", ""))
                    if name:
                        npc_names.append(str(name))
                else:
                    npc_names.append(str(a))
        elif isinstance(actors_data, dict):
            npc_names = list(actors_data.keys())[:5]

        npc_text = f"{', '.join(npc_names)} {'are' if len(npc_names) != 1 else 'is'} {'present' if npc_names else 'absent'}" if npc_names else "You are alone for now"

        # Acknowledge player's action
        action_text = ""
        if player_input:
            action_lower = player_input.lower().strip()
            if any(w in action_lower for w in ("look", "observe", "see", "examine", "search")):
                action_text = "You carefully observe your surroundings. "
            elif any(w in action_lower for w in ("talk", "speak", "ask", "question", "whisper", "say")):
                npc = npc_names[0] if npc_names else "those nearby"
                action_text = f"You try to speak with {npc}. "
            elif any(w in action_lower for w in ("attack", "hit", "strike", "kill", "fight")):
                npc = npc_names[0] if npc_names else "your target"
                action_text = f"You lash out toward {npc}. "
            elif any(w in action_lower for w in ("move", "go", "walk", "run", "leave", "head")):
                loc = scene.get("location", "another area")
                action_text = f"You start to move toward {loc}. "
            elif any(w in action_lower for w in ("take", "grab", "pick up", "use")):
                action_text = "You reach for something. "
            else:
                action_text = f"Your words echo: \"{player_input[:80]}\". "
        else:
            action_text = "You hesitate, weighing your options. "

        title_scene = f"{title}\n\n" if title != "The Scene" else ""

        return (
            f"{title_scene}{action_text}"
            f"{summary}\n\n"
            f"{npc_text}, the weight of the moment pressing down. "
            f"The stakes are clear: {stakes}. "
            f"The air is thick with {tone} tension as the scene unfolds."
        )

    @staticmethod
    def _simulate_npc_reaction(npc_name: str) -> NPCReaction:
        """Generate a simulated NPC reaction without LLM."""
        emotions = ["tense", "curious", "determined", "cautious", "alert"]
        intents = ["observe", "act", "confront", "wait", "negotiate"]
        reactions = [
            f"{npc_name} considers the situation carefully.",
            f"{npc_name}'s expression grows serious.",
            f"{npc_name} shifts uneasily, weighing options.",
            f"{npc_name} meets your gaze with quiet resolve.",
        ]
        dialogues = [
            "We should act quickly.",
            "This changes everything.",
            "I've seen this before.",
            "What do you think we should do?",
        ]
        # Use hash of name for deterministic selection
        idx = hash(npc_name)
        return NPCReaction(
            npc_id=npc_name.lower().replace(" ", "_"),
            npc_name=npc_name,
            reaction=reactions[idx % len(reactions)],
            dialogue=dialogues[idx % len(dialogues)],
            emotion=emotions[idx % len(emotions)],
            intent=intents[idx % len(intents)],
        )

    @staticmethod
    def _simulate_choices(scene: Dict[str, Any], source: str = "") -> List[Dict[str, Any]]:
        """Generate simulated choices without LLM.

        Adapts choices based on player input for more relevant options.
        """
        player_input = scene.get("player_input", "").lower().strip() if isinstance(scene.get("player_input", ""), str) else ""

        # Base choice pool — rotate based on what player did
        if player_input:
            if any(w in player_input for w in ("talk", "speak", "ask", "question")):
                # After talking, offer follow-up options
                return [
                    {"id": "choice_1", "text": "Press for more information", "type": "dialogue", "action": {"type": "escalate_conflict", "target_id": source}},
                    {"id": "choice_2", "text": "Change the subject", "type": "dialogue", "action": {"type": "intervene_thread", "target_id": source}},
                    {"id": "choice_3", "text": "Step back and consider", "type": "observe", "action": {"type": "observe_situation", "target_id": source}},
                ]
            elif any(w in player_input for w in ("look", "observe", "see", "examine", "search")):
                # After observing, offer action options
                return [
                    {"id": "choice_1", "text": "Act on what you've learned", "type": "action", "action": {"type": "intervene_thread", "target_id": source}},
                    {"id": "choice_2", "text": "Investigate further", "type": "observe", "action": {"type": "observe_situation", "target_id": source}},
                    {"id": "choice_3", "text": "Share your findings", "type": "dialogue", "action": {"type": "escalate_conflict", "target_id": source}},
                ]
            elif any(w in player_input for w in ("attack", "hit", "strike", "kill", "fight", "draw")):
                # After combat action, offer escalation
                return [
                    {"id": "choice_1", "text": "Press the attack", "type": "action", "action": {"type": "escalate_conflict", "target_id": source}},
                    {"id": "choice_2", "text": "Stand down", "type": "observe", "action": {"type": "intervene_thread", "target_id": source}},
                    {"id": "choice_3", "text": "Call for parley", "type": "dialogue", "action": {"type": "intervene_thread", "target_id": source}},
                ]
            elif any(w in player_input for w in ("move", "go", "walk", "run", "leave", "head")):
                # After movement
                return [
                    {"id": "choice_1", "text": "Continue forward", "type": "action", "action": {"type": "intervene_thread", "target_id": source}},
                    {"id": "choice_2", "text": "Reassess your route", "type": "observe", "action": {"type": "observe_situation", "target_id": source}},
                    {"id": "choice_3", "text": "Return to where you started", "type": "action", "action": {"type": "intervene_thread", "target_id": source}},
                ]

        # Default varied choices
        return [
            {"id": "choice_1", "text": "Take decisive action", "type": "action", "action": {"type": "intervene_thread", "target_id": source}},
            {"id": "choice_2", "text": "Observe the situation carefully", "type": "observe", "action": {"type": "observe_situation", "target_id": source}},
            {"id": "choice_3", "text": "Speak with those present", "type": "dialogue", "action": {"type": "escalate_conflict", "target_id": source}},
        ]


# ---------------------------------------------------------------------------
# Convenience functions (service layer)
# ---------------------------------------------------------------------------

def _generate_live_narrative(
    scene: Dict[str, Any],
    narration_context: Dict[str, Any],
    llm_gateway: Any,
    tone: str = "dramatic",
    retry_on_invalid: bool = True,
    debug_logging: bool = False,
    on_chunk: Optional[Callable[[str], None]] = None,
    require_live_llm: bool = False,
) -> str:
    """Generate narrative using LLM."""
    # Inject player_input from narration_context into scene
    scene = dict(scene or {})
    if "player_input" not in scene and narration_context:
        pi = narration_context.get("player_input", "")
        if pi:
            scene["player_input"] = str(pi)

    prompt = build_scene_prompt(scene, narration_context, tone=tone)
    if debug_logging:
        logger.warning("[RPG LLM PROMPT]\n%s", prompt)
    else:
        logger.debug("[RPG LLM PROMPT] prompt length: %d", len(prompt))
    max_attempts = 2 if retry_on_invalid else 1
    llm_narrative = ""

    logger.info(
        "[RPG NARRATOR] live_narrative_start prompt_len=%d retry_on_invalid=%s max_attempts=%d",
        len(prompt),
        retry_on_invalid,
        max_attempts,
    )

    import time

    for attempt in range(max_attempts):
        attempt_t0 = time.monotonic()
        logger.info("[RPG NARRATOR] attempt_start attempt=%d/%d", attempt + 1, max_attempts)
        try:
            response = _llm_text(llm_gateway, prompt, context={}, on_chunk=on_chunk if attempt == 0 else None)
            print("[LLM RAW]", repr(response)[:500])
            llm_narrative = _extract_llm_text(response)
            print("[LLM TEXT]", repr(llm_narrative)[:500])
            logger.info(
                "[RPG NARRATOR] attempt_end attempt=%d/%d dt=%.3fs response_len=%d",
                attempt + 1,
                max_attempts,
                time.monotonic() - attempt_t0,
                len(str(llm_narrative or "")),
            )
            if debug_logging:
                logger.warning("[RPG LLM RAW OUTPUT attempt %d]\n%s", attempt + 1, llm_narrative)
            else:
                logger.debug("[RPG LLM RAW OUTPUT attempt %d] length: %d", attempt + 1, len(str(llm_narrative or "")))

            # Check if response contains invalid content (like ambient updates)
            response_lower = _safe_str(llm_narrative).lower()
            if any(phrase in response_lower for phrase in [
                "faction loyalty baseline",
                "maintain awareness",
                "playertick",
                "📜 📜"
            ]):
                logger.error("LLM response contains invalid ambient-like content, rejecting: %s", llm_narrative[:200])
                continue

            parsed = parse_scene_response(llm_narrative)
            if debug_logging:
                logger.warning("[RPG PARSED RESPONSE]\n%s", parsed)
            else:
                logger.debug("[RPG PARSED RESPONSE] keys: %s", list(parsed.keys()) if isinstance(parsed, dict) else type(parsed))

            if _is_valid_scene_response(parsed):
                logger.debug("LLM response validation successful")
                return llm_narrative
            else:
                logger.warning(
                    "[RPG NARRATOR] attempt_rejected attempt=%d/%d reason=invalid_scene_format",
                    attempt + 1,
                    max_attempts,
                )
                logger.error("LLM response failed validation, parsed: %s", parsed)
        except Exception as exc:
            print("[RPG][narrator] provider call failed", {
                "error": repr(exc),
                "traceback": traceback.format_exc()[-4000:],
            })
            if require_live_llm:
                raise
            logger.exception("Exception during LLM narration")

    # fallback if LLM fails format - return raw text for recovery
    logger.error("Structured RPG narration LLM output failed validation after %d attempt(s), returning raw text", max_attempts)
    if require_live_llm:
        raise RuntimeError(
            "live_llm_required_but_llm_failed: empty_response_from_provider"
        )
    return llm_narrative if 'llm_narrative' in locals() and llm_narrative else _structured_fallback_response()


def _simulate_narrative(scene: Dict[str, Any], narration_context: Dict[str, Any], tone: str = "dramatic") -> str:
    """Generate simulated narrative text without LLM.

    Incorporates player input and scene actors for varied responses.
    """
    title = scene.get("title", "The Scene")
    summary = scene.get("summary", "Events unfold around you.")
    stakes = scene.get("stakes", "much is at stake")
    player_input = narration_context.get("player_input", scene.get("player_input", ""))
    actors_data = scene.get("actors", [])

    # Extract NPC names from actor dicts
    npc_names = []
    if isinstance(actors_data, list):
        for a in actors_data[:5]:
            if isinstance(a, dict):
                name = a.get("name", a.get("id", ""))
                if name:
                    npc_names.append(str(name))
            else:
                npc_names.append(str(a))
    elif isinstance(actors_data, dict):
        npc_names = list(actors_data.keys())[:5]

    npc_text = f"{', '.join(npc_names)} {'are' if len(npc_names) != 1 else 'is'} {'present' if npc_names else 'absent'}" if npc_names else "You are alone for now"

    # Acknowledge player's action
    action_text = ""
    if player_input:
        action_lower = player_input.lower().strip()
        if any(w in action_lower for w in ("look", "observe", "see", "examine", "search")):
            action_text = "You carefully observe your surroundings. "
        elif any(w in action_lower for w in ("talk", "speak", "ask", "question", "whisper", "say")):
            npc = npc_names[0] if npc_names else "those nearby"
            action_text = f"You try to speak with {npc}. "
        elif any(w in action_lower for w in ("attack", "hit", "strike", "kill", "fight")):
            npc = npc_names[0] if npc_names else "your target"
            action_text = f"You lash out toward {npc}. "
        elif any(w in action_lower for w in ("move", "go", "walk", "run", "leave", "head")):
            loc = scene.get("location", "another area")
            action_text = f"You start to move toward {loc}. "
        elif any(w in action_lower for w in ("take", "grab", "pick up", "use")):
            action_text = "You reach for something. "
        else:
            action_text = f"Your words echo: \"{player_input[:80]}\". "
    else:
        action_text = "You hesitate, weighing your options. "

    title_scene = f"{title}\n\n" if title != "The Scene" else ""

    return (
        f"{title_scene}{action_text}"
        f"{summary}\n\n"
        f"{npc_text}, the weight of the moment pressing down. "
        f"The stakes are clear: {stakes}. "
        f"The air is thick with {tone} tension as the scene unfolds."
    )


def narrate_scene(
    scene: Dict[str, Any],
    narration_context: Dict[str, Any],
    llm_gateway: Any | None = None,
    tone: str = "dramatic",
    retry_on_invalid: bool = True,
    debug_logging: bool = False,
    on_chunk: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    scene = _safe_dict(scene)
    narration_context = _safe_dict(narration_context)
    require_live_llm = _force_live_llm_required(narration_context)
    print("[RPG][narrator] entering narrate_scene", {
        "require_live_llm": require_live_llm,
        "has_turn_contract": bool(_safe_dict(narration_context.get("turn_contract"))),
        "has_resolved_result": bool(_safe_dict(narration_context.get("resolved_result"))),
    })
    turn_id = narration_context.get("turn_id")
    if turn_id and turn_id in _ACTIVE_NARRATIONS:
        if require_live_llm:
            raise RuntimeError("live_llm_required_but_narrator_fallback_selected")
        return {
            "narration": "",
            "used_llm": False,
            "raw_llm_narrative": "",
            "narration_json": {},
            "speaker_presentation": {},
            "format_warning": False,
        }
    if turn_id:
        _ACTIVE_NARRATIONS.add(turn_id)
    try:
        try_ambient = _safe_str(narration_context.get("mode")) == "ambient_conversation"
        if try_ambient:
            if require_live_llm:
                raise RuntimeError("live_llm_required_but_ambient_fallback_selected")
            text = _build_ambient_conversation_line(narration_context)
            return {
                "narration": text,
                "structured_narration": {"markdown": text, "speaker_turns": []},
                "speaker_turns": [],
                "used_llm": False,
                "raw_llm_narrative": "",
                "llm_error": False,
            }

        if llm_gateway:
            print("[RPG][narrator] provider resolved", {
                "provider_type": type(llm_gateway).__name__ if llm_gateway else "",
                "provider_truthy": bool(llm_gateway),
            })

            if require_live_llm and not llm_gateway:
                raise RuntimeError("live_llm_required_but_no_provider_available")

            llm_narrative = _generate_live_narrative(
                scene,
                narration_context,
                llm_gateway=llm_gateway,
                tone=tone,
                retry_on_invalid=retry_on_invalid,
                debug_logging=debug_logging,
                on_chunk=on_chunk,
                require_live_llm=require_live_llm,
            )

            # Parse JSON response with tolerant fallback
            parsed_json = _parse_llm_narration_payload(llm_narrative)
            print("[RPG][LLM PARSED]", parsed_json)
            if parsed_json and _safe_str(parsed_json.get("format_version")) == "rpg_narration_v2":
                narration_json = _strict_narration_payload(parsed_json)
            else:
                narration_json = _strict_narration_payload(_normalize_narration_json(parsed_json or {}))

            print("[RPG][LLM RAW ACTION]", _safe_dict(parsed_json).get("action"))
            print("[RPG][STRICT ACTION]", narration_json.get("action"))

            if not narration_json.get("narration") and not narration_json.get("action") and not _safe_str(_safe_dict(narration_json.get("npc")).get("line")).strip():
                logger.warning("Narration JSON parse failed or empty; recovering from raw text")
                narration_json = _strict_narration_payload(_recover_narration_from_raw_text(llm_narrative))

            print("[RPG][PRE-SANITIZE ACTION]", narration_json.get("action"))
            authoritative_action = _build_authoritative_action_line(narration_context)
            grounded_json = _sanitize_narration_payload(narration_json, scene, narration_context, authoritative_action=authoritative_action)

            print("[RPG][SANITIZED ACTION]", grounded_json.get("action"))

            parts = []

            if grounded_json["narration"]:
                parts.append(grounded_json["narration"])

            if authoritative_action:
                parts.append(authoritative_action)

            llm_action = _safe_str(grounded_json.get("action")).strip()
            if llm_action and llm_action != authoritative_action:
                parts.append(f"Result: {llm_action}")

            npc = _safe_dict(grounded_json.get("npc"))
            if npc.get("speaker") and npc.get("line"):
                parts.append(f"{npc['speaker']}: \"{npc['line']}\"")

            rendered_narration = _naturalize_service_debug_language("\n\n".join(parts).strip())

            return {
                "narration": rendered_narration,
                "used_llm": True,
                "raw_llm_narrative": llm_narrative,
                "narration_json": grounded_json,
                "speaker_presentation": {},
                "format_warning": False,
            }
        else:
            if require_live_llm:
                raise RuntimeError("live_llm_required_but_simulation_fallback_selected")
            llm_narrative = _simulate_narrative(scene, narration_context, tone=tone)
            simulated_json = _normalize_narration_json({
                "narration": llm_narrative,
                "action": _authoritative_action_text(narration_context),
                "npc": {"speaker": "", "line": ""},
                "reward": _authoritative_reward_text(narration_context),
                "followup_hooks": [],
            })
            narration_json = _strict_narration_payload(simulated_json)
            print("[RPG][LLM RAW ACTION]", _safe_dict(simulated_json).get("action"))
            print("[RPG][STRICT ACTION]", narration_json.get("action"))
            print("[RPG][PRE-SANITIZE ACTION]", narration_json.get("action"))
            authoritative_action = _build_authoritative_action_line(narration_context)
            grounded_json = _sanitize_narration_payload(narration_json, scene, narration_context, authoritative_action=authoritative_action)

            print("[RPG][SANITIZED ACTION]", grounded_json.get("action"))

            parts = []

            if grounded_json["narration"]:
                parts.append(grounded_json["narration"])

            if authoritative_action:
                parts.append(authoritative_action)

            llm_action = _safe_str(grounded_json.get("action")).strip()
            if llm_action and llm_action != authoritative_action:
                parts.append(f"Result: {llm_action}")

            npc = _safe_dict(grounded_json.get("npc"))
            if npc.get("speaker") and npc.get("line"):
                parts.append(f"{npc['speaker']}: \"{npc['line']}\"")

            rendered_narration = _naturalize_service_debug_language("\n\n".join(parts).strip())

            return {
                "narration": rendered_narration,
                "used_llm": False,
                "raw_llm_narrative": llm_narrative,
                "narration_json": grounded_json,
                "speaker_presentation": {},
                "format_warning": False,
            }
    finally:
        if turn_id:
            _ACTIVE_NARRATIONS.discard(turn_id)


def play_scene(
    scene: Dict[str, Any],
    state: Dict[str, Any],
    *,
    llm_gateway: Optional[Any] = None,
    tone: str = "dramatic",
) -> Dict[str, Any]:
    """Play a scene and return narrated result as dict.

    This is the main service function called by routes.

    Args:
        scene: Scene dict to play.
        state: Game state dict.
        llm_gateway: Optional LLM gateway for real narration.
        tone: Narrative tone.

    Returns:
        Dict suitable for JSON response.
    """
    narrator = SceneNarrator(
        llm_gateway=llm_gateway,
        default_tone=tone,
        simulate_mode=not bool(llm_gateway),
    )
    result = narrator.narrate_scene(scene, state, tone=tone)

    return {
        "narrative": result.narrative,
        "choices": result.choices,
        "npc_reactions": [
            {
                "npc_id": r.npc_id,
                "npc_name": r.npc_name,
                "dialogue": r.dialogue,
                "emotion": r.emotion,
                "intent": r.intent,
            }
            for r in result.npc_reactions
        ],
        "dialogue_blocks": result.dialogue_blocks,
        "metadata": result.metadata,
    }


def apply_legacy_narration_emphasis(narration_payload: dict) -> dict:
    """Apply markdown emphasis to important narration elements.

    Deterministically formats structured result fields — does NOT ask
    the LLM to bold things randomly.
    """
    import re
    payload = dict(narration_payload or {})
    text = str(payload.get("narration") or payload.get("text") or payload.get("content") or "")

    if not text:
        return payload

    # Bold item names (from items list if available)
    items = payload.get("items", [])
    for item in (items if isinstance(items, list) else []):
        if isinstance(item, dict):
            name = str(item.get("name", ""))
            if name and len(name) > 2:
                text = text.replace(name, f"**{name}**")

    # Bold quest updates
    text = re.sub(r'(?i)(quest updated?:?\s*)', r'**\1**', text)
    text = re.sub(r'(?i)(quest complete[d]?:?\s*)', r'**\1**', text)

    # Bold damage numbers
    text = re.sub(r'(\d+)\s+(damage)', r'**\1 \2**', text)

    # Bold level ups
    text = re.sub(r'(?i)(level up!?)', r'**\1**', text)
    text = re.sub(r'(?i)(leveled? up!?)', r'**\1**', text)

    # Bold named enemies in combat results
    combat = payload.get("combat_result", {})
    if isinstance(combat, dict):
        enemy_name = str(combat.get("enemy_name") or combat.get("target_name") or "")
        if enemy_name and len(enemy_name) > 2:
            text = text.replace(enemy_name, f"**{enemy_name}**")

    # Avoid double-bold
    text = text.replace("****", "**")

    # Update payload
    if "narration" in payload:
        payload["narration"] = text
    elif "text" in payload:
        payload["text"] = text
    elif "content" in payload:
        payload["content"] = text

    return payload


# ── Living-world: ambient narration (Phase 5) ─────────────────────────────

_AMBIENT_TEMPLATES = {
    "npc_to_player": "{speaker_name} turns to you: \"{text}\"",
    "npc_to_npc": "{speaker_name} speaks to {target_name}: \"{text}\"",
    "npc_reaction": "{speaker_name} reacts: \"{text}\"",
    "companion_comment": "{speaker_name} says: \"{text}\"",
    "warning": "{speaker_name} warns: \"{text}\"",
    "demand": "{speaker_name} demands: \"{text}\"",
    "taunt": "{speaker_name} taunts: \"{text}\"",
    "gossip": "{speaker_name} mutters: \"{text}\"",
    "world_event": "{text}",
    "arrival": "{text}",
    "departure": "{text}",
    "combat_start": "⚔️ {text}",
    "system_summary": "📜 {text}",
}

_AMBIENT_PROMPTS = {
    "npc_to_player": (
        "You are {speaker_name}, an NPC in a living fantasy world. "
        "Write one short sentence addressed to the player. "
        "Emotion: {emotion}. Context: {context}. "
        "Respond ONLY with the spoken line, no quotation marks."
    ),
    "npc_to_npc": (
        "You are {speaker_name}, an NPC. Write one short sentence spoken to {target_name}. "
        "Emotion: {emotion}. Context: {context}. "
        "Respond ONLY with the spoken line, no quotation marks."
    ),
    "companion_comment": (
        "You are {speaker_name}, a companion of the player. "
        "Write one short observation or comment about the current situation. "
        "Context: {context}. "
        "Respond ONLY with the spoken line, no quotation marks."
    ),
    "warning": (
        "You are {speaker_name}. Write a brief, tense warning directed at the player. "
        "Context: {context}. "
        "Respond ONLY with the spoken line, no quotation marks."
    ),
    "world_event": (
        "Write one concise sentence narrating this world event for the player: {text}. "
        "Context: {context}. "
        "Respond ONLY with the narration sentence."
    ),
    "system_summary": (
        "Summarize these world changes in one or two sentences for a returning player: {text}. "
        "Context: {context}. "
        "Respond ONLY with the summary."
    ),
}


def narrate_ambient_update(
    *,
    ambient_update: Dict[str, Any],
    simulation_state: Dict[str, Any],
    current_scene: Dict[str, Any],
    llm_gateway: Any = None,
) -> Dict[str, Any]:
    """Narrate an ambient update for player presentation.
    
    If LLM is available, uses it for stylistic phrasing.
    Always falls back to deterministic templates if LLM is unavailable.
    LLM only styles phrasing — never invents world truth.
    
    Returns:
        {
            "text": str,
            "speaker_turns": list,
            "used_app_llm": bool,
            "raw_llm_narrative": str,
            "structured": dict,
        }
    """
    ambient_update = _safe_dict(ambient_update)
    simulation_state = _safe_dict(simulation_state)
    current_scene = _safe_dict(current_scene)
    
    kind = _safe_str(ambient_update.get("kind"))
    speaker_id = _safe_str(ambient_update.get("speaker_id"))
    speaker_name = _safe_str(ambient_update.get("speaker_name")) or speaker_id
    target_name = _safe_str(ambient_update.get("target_name"))
    raw_text = _safe_str(ambient_update.get("text"))
    emotion = _safe_str(ambient_update.get("emotion")) or "neutral"
    
    # Build scene context summary for LLM prompt
    scene_summary = _safe_str(current_scene.get("summary") or current_scene.get("scene"))
    context = scene_summary[:200] if scene_summary else "The world stirs."
    
    used_llm = False
    raw_llm_narrative = ""
    narrated_text = raw_text
    
    # Try LLM narration if available
    if llm_gateway and kind in _AMBIENT_PROMPTS:
        try:
            prompt_template = _AMBIENT_PROMPTS[kind]
            prompt = prompt_template.format(
                speaker_name=speaker_name,
                target_name=target_name,
                emotion=emotion,
                context=context,
                text=raw_text,
            )
            llm_response = _llm_text(llm_gateway, prompt)
            if llm_response and "[ERROR:" not in llm_response:
                narrated_text = _bound_text(llm_response.strip(), 250)
                raw_llm_narrative = llm_response
                used_llm = True
        except Exception:
            pass  # Fall through to template
    
    # Template fallback
    if not used_llm:
        template = _AMBIENT_TEMPLATES.get(kind, "{text}")
        narrated_text = template.format(
            speaker_name=speaker_name,
            target_name=target_name,
            text=raw_text,
        )
    
    # Build speaker turns for dialogue rendering
    speaker_turns: List[Dict[str, Any]] = []
    if speaker_id and kind in ("npc_to_player", "npc_to_npc", "companion_comment", "warning", "demand", "taunt", "gossip", "npc_reaction"):
        speaker_turns.append({
            "speaker_id": speaker_id,
            "name": speaker_name,
            "text": narrated_text,
            "emotion": emotion,
            "ambient": True,
        })
    
    return {
        "text": narrated_text,
        "speaker_turns": speaker_turns,
        "used_app_llm": used_llm,
        "raw_llm_narrative": raw_llm_narrative,
        "structured": {
            "kind": kind,
            "speaker_id": speaker_id,
            "speaker_name": speaker_name,
            "target_id": _safe_str(ambient_update.get("target_id")),
            "target_name": target_name,
            "ambient": True,
        },
    }