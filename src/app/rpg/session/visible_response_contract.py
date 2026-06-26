"""Canonical visible-response guards for RPG turns.

This module is deliberately pure and conservative. Raw provider metadata such as
``tool_calls: []`` may be useful diagnostics, but it must never become player-
facing RPG text.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

_INVALID_VISIBLE_STRINGS = {
    "",
    "[]",
    "[ ]",
    "{}",
    "{ }",
    "null",
    "none",
    "undefined",
    "nan",
    "[object object]",
}
_PROVIDER_METADATA_KEYS = {
    "tool_calls",
    "reasoning_content",
    "usage",
    "stats",
    "system_fingerprint",
    "logprobs",
    "finish_reason",
}
_VISIBLE_STRING_KEYS = (
    "visible_text",
    "final_narration",
    "narration",
    "summary",
    "text",
    "content",
    "action",
)


def _d(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _l(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _s(value: Any) -> str:
    return str(value) if value is not None else ""


def _norm_text(value: Any) -> str:
    return _s(value).strip().casefold()


def _is_invalid_string(value: Any) -> bool:
    text = _norm_text(value)
    if text in _INVALID_VISIBLE_STRINGS:
        return True
    if not text:
        return True
    if text.startswith("model generated tool calls"):
        return True
    if text in {"tool_calls: []", "\"tool_calls\": []"}:
        return True
    alpha_num = sum(1 for char in text if char.isalnum())
    return len(text) > 1 and alpha_num == 0


def extract_provider_message_content(response: Any) -> str:
    """Extract assistant message content from OpenAI/LM Studio shaped payloads.

    Explicitly ignores provider metadata fields such as ``tool_calls``. The bug
    this guards against was selecting ``tool_calls: []`` instead of
    ``choices[0].message.content``.
    """

    data = _d(response)
    if not data:
        return ""

    choices = _l(data.get("choices"))
    if choices:
        first = _d(choices[0])
        message = _d(first.get("message"))
        content = message.get("content")
        if isinstance(content, str) and not _is_invalid_string(content):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = _s(item.get("text") or item.get("content")).strip()
                    if text:
                        parts.append(text)
            joined = "\n".join(part.strip() for part in parts if part.strip()).strip()
            if joined and not _is_invalid_string(joined):
                return joined

    message = _d(data.get("message"))
    content = message.get("content")
    if isinstance(content, str) and not _is_invalid_string(content):
        return content.strip()

    for key in ("text", "content"):
        value = data.get(key)
        if isinstance(value, str) and not _is_invalid_string(value):
            return value.strip()
    return ""


def visible_response_text(value: Any) -> str:
    """Return canonical user-visible text from a bounded RPG result object."""

    if value is None or isinstance(value, (list, tuple, set)):
        return ""
    if isinstance(value, str):
        return "" if _is_invalid_string(value) else value.strip()

    data = _d(value)
    if not data:
        return ""

    provider_content = extract_provider_message_content(data)
    if provider_content:
        return provider_content

    visible_response = _d(data.get("visible_response"))
    if visible_response:
        text = visible_response_text(visible_response)
        if text:
            return text

    nested_result = _d(data.get("result"))
    if nested_result:
        text = visible_response_text(nested_result)
        if text:
            return text

    authoritative = _d(data.get("authoritative"))
    if authoritative:
        text = visible_response_text(authoritative)
        if text:
            return text

    npc = _d(data.get("npc"))
    speaker = _s(npc.get("speaker")).strip()
    line = _s(npc.get("line")).strip()
    if line and not _is_invalid_string(line):
        return f"{speaker}: {line}" if speaker else line

    for key in _VISIBLE_STRING_KEYS:
        value_for_key = data.get(key)
        if isinstance(value_for_key, str) and not _is_invalid_string(value_for_key):
            return value_for_key.strip()

    return ""


def is_invalid_visible_value(value: Any) -> bool:
    """True when a candidate must not be shown as RPG-visible text."""

    if value is None:
        return True
    if isinstance(value, str):
        return _is_invalid_string(value)
    if isinstance(value, (list, tuple, set)):
        return True
    data = _d(value)
    if not data:
        return True
    if set(data.keys()).issubset(_PROVIDER_METADATA_KEYS):
        return True
    return not bool(visible_response_text(data))


def invalid_visible_selection_reason(selection: Any) -> str:
    """Return a rejection reason for a consumable first-call selection."""

    data = _d(selection)
    if not data or not data.get("consumable"):
        return ""
    visible = _d(data.get("visible_response")) or data
    if is_invalid_visible_value(visible):
        return "invalid_visible_response_text"
    return ""


def build_visible_turn_record(result: Any, *, player_input: str = "") -> dict[str, Any]:
    data = _d(result)
    visible_text = visible_response_text(data)
    rejected: list[dict[str, Any]] = []
    for label, candidate in (
        ("top_level_tool_calls", data.get("tool_calls")),
        ("top_level_text", data.get("text")),
        ("top_level_content", data.get("content")),
        ("visible_response", data.get("visible_response")),
    ):
        if candidate is not None and is_invalid_visible_value(candidate):
            rejected.append({"source": label, "reason": "invalid_visible_value", "value_type": type(candidate).__name__})
    return {
        "format_version": "rpg_visible_turn_record_v1",
        "player_input": _s(player_input),
        "visible_text": visible_text,
        "visible_text_valid": bool(visible_text),
        "rejected_visible_candidates": rejected,
        "source": "visible_response_contract_v1",
    }


def attach_visible_turn_record(result: Any, *, player_input: str = "") -> Any:
    if not isinstance(result, dict):
        return result
    data = deepcopy(result)
    record = build_visible_turn_record(data, player_input=player_input or _s(data.get("player_input")))
    data["visible_turn_record"] = record
    if record["visible_text"]:
        data["visible_text"] = record["visible_text"]
    return data
