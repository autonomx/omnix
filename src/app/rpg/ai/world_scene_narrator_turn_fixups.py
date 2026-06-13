"""Runtime fixups for current-turn narration grounding.

This module is imported last by the world_scene_narrator facade.  It keeps the
fix narrow and reversible while patching the split narration modules that cache
helpers through star imports.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict

from app.rpg.ai import world_scene_narrator_prompts as _prompts
from app.rpg.ai import world_scene_narrator_service_grounding as _service


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _trim(value: Any, limit: int = 180) -> str:
    text = " ".join(_safe_str(value).split()).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _extract_json_object(text: str) -> Dict[str, Any]:
    text = _safe_str(text).strip()
    if not text:
        return {}

    # Strip common wrappers seen from local chat models.
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s*```$", "", text).strip()
    response_match = re.search(r"<RESPONSE>\s*(.*?)\s*</RESPONSE>", text, re.DOTALL | re.IGNORECASE)
    if response_match:
        text = response_match.group(1).strip()

    candidates = [text]
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _unwrap_narration_candidate(parsed_json: Dict[str, Any]) -> Dict[str, Any]:
    """Return the selected rpg_narration_v2 payload from wrapper formats."""

    parsed_json = _safe_dict(parsed_json)
    if parsed_json.get("format_version") == "rpg_narration_candidates_v1":
        primary = _safe_dict(parsed_json.get("primary"))
        if _payload_has_visible_content(primary):
            return primary
        fallback = _safe_dict(parsed_json.get("safe_fallback"))
        if _payload_has_visible_content(fallback):
            return fallback
        return {}
    return parsed_json


def _payload_has_visible_content(payload: Dict[str, Any]) -> bool:
    payload = _safe_dict(payload)
    npc = _safe_dict(payload.get("npc"))
    blob = "\n".join(
        [
            _safe_str(payload.get("narration")),
            _safe_str(payload.get("action")),
            _safe_str(npc.get("line") or npc.get("text")),
        ]
    ).strip()
    return bool(blob)


def parse_scene_response(text: str) -> Dict[str, Any]:
    """Parse direct narration JSON and candidate-wrapper JSON.

    The prompt can legitimately request rpg_narration_candidates_v1.  The old
    parser treated that valid wrapper as empty because it only looked for top
    level narration/action/npc fields, which caused invalid_scene_format and
    allowed stale/fallback dialogue to surface.
    """

    parsed_json = _extract_json_object(text)
    if parsed_json:
        payload = _unwrap_narration_candidate(parsed_json)
        npc = _safe_dict(payload.get("npc"))
        speaker = _safe_str(npc.get("speaker") or npc.get("name")).strip()
        line = _safe_str(npc.get("line") or npc.get("text")).strip()
        return {
            "narrator": _safe_str(payload.get("narration")).strip(),
            "action": _safe_str(payload.get("action")).strip(),
            "npc": {
                "speaker_id": speaker.replace(" ", "_").lower(),
                "name": speaker,
                "text": _trim(line, 180),
                "emotion": "",
                "portrait": "",
            },
            "reward": _safe_str(payload.get("reward")).strip(),
        }

    # Preserve legacy text parsing for non-JSON providers.
    return _ORIGINAL_PARSE_SCENE_RESPONSE(text)


def _player_input_action_text(narration_context: Dict[str, Any]) -> str:
    """Return a safe visible echo of the user's current action.

    Question-style input such as "do you have room...?" must not be prefixed as
    "You do you...".  Treat it as spoken dialogue instead of a verb phrase.
    """

    narration_context = _safe_dict(narration_context)
    turn_contract = _safe_dict(narration_context.get("turn_contract"))
    narration_brief = _safe_dict(turn_contract.get("narration_brief"))
    semantic_action = _safe_dict(turn_contract.get("semantic_action"))

    text = ""
    for value in (
        narration_context.get("player_input"),
        turn_contract.get("player_input"),
        narration_brief.get("summary"),
        semantic_action.get("player_input"),
        _safe_dict(narration_context.get("last_player_action")).get("text"),
    ):
        text = _safe_str(value).strip()
        if text:
            break

    text = _strip_basic_markdown(text)
    if not text:
        return ""

    lowered = text.lower()
    question_starters = (
        "do you ",
        "does ",
        "did ",
        "can you ",
        "could you ",
        "would you ",
        "will you ",
        "are you ",
        "is there ",
        "are there ",
        "have you ",
        "what ",
        "where ",
        "when ",
        "why ",
        "how ",
        "who ",
    )
    if lowered.startswith(question_starters) or text.endswith("?"):
        spoken = text[:1].upper() + text[1:]
        if not spoken.endswith("?"):
            spoken += "?"
        return f'You ask, "{spoken}"'

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


def _service_claim_needs_grounding(text: str) -> bool:
    """Broaden service grounding to catch ungrounded lodging drift."""

    if _ORIGINAL_SERVICE_CLAIM_NEEDS_GROUNDING(text):
        return True
    lower = _safe_str(text).lower()
    drift_terms = (
        "berth",
        "berths",
        "bunk",
        "bunks",
        "shared cot",
        "captain's quarters",
        "captains quarters",
        "ship",
        "shore tonight",
        "lower quarters",
    )
    return any(term in lower for term in drift_terms)


def _strip_basic_markdown(value: Any) -> str:
    text = _safe_str(value).strip()
    if not text:
        return ""
    for marker in ("**", "__", "`"):
        text = text.replace(marker, "")
    return " ".join(text.split()).strip()


_ORIGINAL_PARSE_SCENE_RESPONSE = _prompts.parse_scene_response
_ORIGINAL_SERVICE_CLAIM_NEEDS_GROUNDING = _service._service_claim_needs_grounding

# Patch split modules that imported helpers before the facade import completes.
_prompts.parse_scene_response = parse_scene_response
_service._player_input_action_text = _player_input_action_text
_service._service_claim_needs_grounding = _service_claim_needs_grounding

try:  # Runtime has already star-imported the original helpers during facade load.
    from app.rpg.ai import world_scene_narrator_runtime as _runtime

    _runtime.parse_scene_response = parse_scene_response
    _runtime._player_input_action_text = _player_input_action_text
    _runtime._service_claim_needs_grounding = _service_claim_needs_grounding
except Exception:
    pass

try:
    from app.rpg.ai import world_scene_narrator_structured as _structured

    _structured.parse_scene_response = parse_scene_response
except Exception:
    pass

__all__ = [
    "parse_scene_response",
    "_player_input_action_text",
    "_service_claim_needs_grounding",
]
