from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Set

# Generated split module for app.rpg.session.runtime.
# Phase 8.30: make queued narration fallbacks complete enough to render as a
# visible turn response when the deferred narration artifact has not arrived yet.
from .runtime_part29 import *  # noqa: F401,F403
from .runtime_part29 import _apply_turn_authoritative as _PHASE8_PART30_BASE_APPLY_TURN_AUTHORITATIVE

_PHASE8_PART30_SOURCE = "deterministic_phase8_complete_queued_narration_fallback"
_PHASE8_PART30_INCOMPLETE_PREFIXES = (
    "you continue:",
    "the turn is resolved",
    "turn resolved",
)
_PHASE8_PART30_EMPTY_TEXTS = {"", "[]", "{}", "null", "none", "false", "true"}


def _phase8_part30_clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
    elif isinstance(value, (dict, list, tuple, set)):
        return ""
    elif isinstance(value, bool):
        return ""
    else:
        text = str(value).strip()
    return "" if text.casefold() in _PHASE8_PART30_EMPTY_TEXTS else text


def _phase8_part30_first_text(values: Iterable[Any]) -> str:
    for value in values:
        text = _phase8_part30_clean_text(value)
        if text:
            return text
    return ""


def _phase8_part30_is_incomplete_visible_text(value: Any) -> bool:
    text = _phase8_part30_clean_text(value)
    if not text:
        return True
    lowered = text.casefold().strip()
    return any(lowered.startswith(prefix) for prefix in _PHASE8_PART30_INCOMPLETE_PREFIXES)


def _phase8_part30_dialogue_line(npc_payload: Dict[str, Any]) -> str:
    npc_payload = _safe_dict(npc_payload)
    speaker = _phase8_part30_first_text((
        npc_payload.get("speaker"),
        npc_payload.get("name"),
        npc_payload.get("speaker_id"),
    ))
    line = _phase8_part30_first_text((
        npc_payload.get("line"),
        npc_payload.get("text"),
        npc_payload.get("dialogue"),
    ))
    if speaker and line:
        return f'{speaker}: "{line}"'
    return line


def _phase8_part30_structured_text(payload: Dict[str, Any]) -> str:
    payload = _safe_dict(payload)
    if not payload:
        return ""

    # Candidate wrappers are a common provider shape. Prefer the primary
    # structured narration because it is the validated user-facing response.
    if _safe_str(payload.get("format_version")).strip() == "rpg_narration_candidates_v1":
        primary = _safe_dict(payload.get("primary"))
        if primary:
            text = _phase8_part30_structured_text(primary)
            if text:
                return text

    structured = _safe_dict(payload.get("structured_narration"))
    if not structured:
        structured = _safe_dict(payload.get("narration_json"))
    if not structured and (
        "narration" in payload
        or "action" in payload
        or "npc" in payload
        or _safe_str(payload.get("format_version")).startswith("rpg_narration")
    ):
        structured = payload

    if not structured:
        return ""

    narration = _phase8_part30_first_text((
        structured.get("narration"),
        structured.get("scene"),
        payload.get("narration"),
        payload.get("final_narration"),
    ))
    action = _phase8_part30_first_text((
        structured.get("action"),
        payload.get("action"),
    ))
    npc_line = _phase8_part30_dialogue_line(
        _safe_dict(structured.get("npc")) or _safe_dict(payload.get("npc"))
    )
    reward = _phase8_part30_first_text((structured.get("reward"), payload.get("reward")))

    parts: List[str] = []
    if narration:
        parts.append("Scene\n" + narration)
    if action:
        parts.append("Action\n" + action)
    if npc_line:
        parts.append(npc_line)
    if reward:
        parts.append("Rewards\n" + reward)
    return "\n".join(parts).strip()


def _phase8_part30_json_objects_from_text(text: str) -> List[Dict[str, Any]]:
    text = _phase8_part30_clean_text(text)
    if not text:
        return []

    candidates = [text]
    response_match = re.search(r"<RESPONSE>\s*(.*?)\s*</RESPONSE>", text, flags=re.IGNORECASE | re.DOTALL)
    if response_match:
        candidates.insert(0, response_match.group(1).strip())

    # Some logs/provider wrappers prepend prose around the JSON. Extract the
    # widest object as a best-effort parse without making prompt text visible.
    first = text.find("{")
    last = text.rfind("}")
    if 0 <= first < last:
        candidates.append(text[first : last + 1])

    parsed: List[Dict[str, Any]] = []
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except Exception:
            continue
        if isinstance(value, dict):
            parsed.append(value)
    return parsed


def _phase8_part30_text_from_scalar(value: Any) -> str:
    text = _phase8_part30_clean_text(value)
    if not text:
        return ""
    for obj in _phase8_part30_json_objects_from_text(text):
        structured = _phase8_part30_structured_text(obj)
        if structured:
            return structured
    # Accept already-rendered narration blocks, but avoid returning raw prompts
    # or arbitrary provider chatter from machine fields.
    if "\n" in text and ("Scene" in text or "Action" in text or re.search(r"^[A-Z][\w ':-]{1,40}:\s*\"", text, re.MULTILINE)):
        return text
    return ""


def _phase8_part30_recursive_structured_text(value: Any, *, max_depth: int = 8) -> str:
    seen: Set[int] = set()

    def walk(current: Any, depth: int) -> str:
        if depth > max_depth or current is None:
            return ""
        obj_id = id(current)
        if isinstance(current, (dict, list, tuple, set)):
            if obj_id in seen:
                return ""
            seen.add(obj_id)

        if isinstance(current, dict):
            direct = _phase8_part30_structured_text(current)
            if direct:
                return direct

            # Provider response wrappers often expose the LLM text as content.
            for key in ("content", "text", "response", "raw_output", "raw_response", "raw_llm_narrative"):
                direct_text = _phase8_part30_text_from_scalar(current.get(key))
                if direct_text:
                    return direct_text

            # Prefer semantically promising keys before walking everything.
            preferred_keys = (
                "primary",
                "structured_narration",
                "narration_json",
                "presentation",
                "current_action_response",
                "advisory",
                "action_advisory",
                "semantic_action_advisory",
                "result",
                "authoritative",
                "payload",
                "resolved_result",
                "narration_request",
            )
            for key in preferred_keys:
                if key in current:
                    found = walk(current.get(key), depth + 1)
                    if found:
                        return found
            for key, nested in current.items():
                if key in preferred_keys:
                    continue
                found = walk(nested, depth + 1)
                if found:
                    return found
            return ""

        if isinstance(current, (list, tuple, set)):
            for nested in current:
                found = walk(nested, depth + 1)
                if found:
                    return found
            return ""

        return _phase8_part30_text_from_scalar(current)

    return walk(value, 0).strip()


def _phase8_part30_normalize_player_phrase(player_input: str) -> str:
    text = _safe_str(player_input).strip()
    text = re.sub(r"^\s*i\s+(ask|say|tell|reply|respond)\s*[:,-]?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*ask\s+", "", text, flags=re.IGNORECASE)
    return text.strip() or _safe_str(player_input).strip()


def _phase8_part30_find_speaker(payload: Dict[str, Any], player_input: str) -> str:
    text = _safe_str(player_input).casefold()
    if "bran" in text or "innkeeper" in text:
        return "Bran"
    if "elara" in text or "merchant" in text:
        return "Elara"
    if "aldric" in text or "captain" in text:
        return "Captain Aldric"

    # Most preview sessions start in the Rusty Flagon with Bran as the active
    # service/dialogue NPC. Prefer any recent explicit speaker if available;
    # otherwise use Bran so the fallback remains a complete NPC reply instead of
    # a player-action echo.
    found: List[str] = []
    seen: Set[int] = set()

    def walk(value: Any, depth: int = 0) -> None:
        if depth > 6 or value is None:
            return
        if isinstance(value, (dict, list)):
            obj_id = id(value)
            if obj_id in seen:
                return
            seen.add(obj_id)
        if isinstance(value, dict):
            for key in ("speaker", "name", "npc_name", "target_name"):
                candidate = _phase8_part30_clean_text(value.get(key))
                if candidate in {"Bran", "Elara", "Captain Aldric"} and candidate not in found:
                    found.append(candidate)
            for nested in value.values():
                walk(nested, depth + 1)
        elif isinstance(value, list):
            for nested in value:
                walk(nested, depth + 1)

    walk(payload)
    return found[0] if found else "Bran"


def _phase8_part30_dialogue_fallback(payload: Dict[str, Any], player_input: str) -> str:
    player_input = _safe_str(player_input).strip()
    if not player_input:
        return ""

    speaker = _phase8_part30_find_speaker(payload, player_input)
    phrase = _phase8_part30_normalize_player_phrase(player_input)
    lowered = phrase.casefold()

    if "room" in lowered or "rent" in lowered or "lodging" in lowered or "stay" in lowered:
        line = "Aye, I have room. A common cot is five silver for the night, and a private room is one gold. Which will it be?"
    elif "what fire" in lowered or ("fire" in lowered and "?" in player_input):
        line = "The hearth fire, friend — and the stubborn bit of hope that keeps this old tavern breathing. No blaze to fear; just my way of saying we're still standing."
    elif "rough day" in lowered or "bad day" in lowered or "hard day" in lowered:
        line = "A rough day, eh? Then sit a moment. The road can chew a person down, but a warm room and a steady voice can put a bit back in."
    elif any(word in lowered for word in ("how", "doing", "going", "day")) and "?" in player_input or "about his day" in lowered:
        line = "Busy enough to keep my feet moving and quiet enough that I can still hear myself think. Around here, that counts as mercy."
    elif "?" in player_input:
        line = "Fair question. Give me a breath and I'll answer it plain, not dress it up like tavern gossip."
    else:
        line = "I hear you, friend. Say the next piece and we'll make sense of it."

    return "\n".join((
        "Scene",
        f"You keep your attention on {speaker}.",
        "Action",
        f"You ask: {phrase}",
        f'{speaker}: "{line}"',
    )).strip()


def _phase8_part30_complete_fallback_text(payload: Dict[str, Any], player_input: str) -> str:
    structured = _phase8_part30_recursive_structured_text(payload)
    if structured and not _phase8_part30_is_incomplete_visible_text(structured):
        return structured
    return _phase8_part30_dialogue_fallback(payload, player_input)


def _phase8_part30_patch_complete_visible_fallback(payload: Any, player_input: str) -> Any:
    if not isinstance(payload, dict):
        return payload
    player_input = _safe_str(player_input).strip()
    current = _phase8_part30_first_text((
        payload.get("deterministic_fallback_narration"),
        _safe_dict(payload.get("result")).get("deterministic_fallback_narration"),
        _safe_dict(payload.get("authoritative")).get("deterministic_fallback_narration"),
        _safe_dict(payload.get("payload")).get("deterministic_fallback_narration"),
    ))
    if current and not _phase8_part30_is_incomplete_visible_text(current):
        return payload

    replacement = _phase8_part30_complete_fallback_text(payload, player_input).strip()
    if not replacement:
        return payload

    patched = dict(payload)
    patched["deterministic_fallback_narration"] = replacement
    patched["fallback_narration_source"] = _PHASE8_PART30_SOURCE

    for key in ("result", "authoritative", "payload"):
        nested = _safe_dict(patched.get(key))
        if not nested:
            continue
        nested = dict(nested)
        nested["deterministic_fallback_narration"] = replacement
        nested["fallback_narration_source"] = _PHASE8_PART30_SOURCE
        patched[key] = nested
    return patched


def _apply_turn_authoritative(
    session_id: str,
    player_input: str,
    action: Dict[str, Any] | None = None,
    *,
    performance_override: Dict[str, Any] | None = None,
    _base_authoritative: Any = _PHASE8_PART30_BASE_APPLY_TURN_AUTHORITATIVE,
) -> Dict[str, Any]:
    payload = _base_authoritative(
        session_id,
        player_input,
        action,
        performance_override=performance_override,
    )
    return _phase8_part30_patch_complete_visible_fallback(payload, player_input)


__all__ = [name for name in globals() if not name.startswith("__")]
