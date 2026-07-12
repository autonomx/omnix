"""Canonical visible-response extraction for every RPG delivery path."""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Iterable

_FORMAT_VERSION = "rpg_visible_response_v1"
_NON_NPC_SPEAKERS = {
    "",
    "scene",
    "narrator",
    "narration",
    "gm",
    "game master",
    "omnix",
    "system",
    "player",
    "you",
}


def build_visible_response(result: Any, fallback_command: str = "") -> dict[str, Any]:
    """Return one bounded narration/dialogue contract from a nested turn result."""

    sources = list(_iter_sources(result))
    narration = _first_text(
        sources,
        "narration",
        "final_narration",
        "summary",
        "response",
        "content",
        "text",
    )
    npc = _first_npc(sources)
    speaker = _text(npc.get("speaker") or npc.get("name"))
    line = _text(npc.get("line") or npc.get("text") or npc.get("content"))
    speaker_norm = _normalize(speaker)
    if speaker_norm in _NON_NPC_SPEAKERS:
        speaker = ""
        line = ""

    messages: list[dict[str, Any]] = []
    if line:
        messages.append(
            {
                "kind": "npc_dialogue",
                "speaker_id": _text(npc.get("speaker_id") or npc.get("npc_id") or npc.get("id")) or None,
                "speaker": speaker or "NPC",
                "text": _normalize_dialogue_quotes(line),
            }
        )

    paragraphs: list[str] = []
    if narration and not _equivalent(narration, line):
        paragraphs.append(narration)
    if line:
        quoted = _normalize_dialogue_quotes(line)
        paragraphs.append(f'{speaker or "NPC"}: "{quoted}"')

    if not paragraphs:
        fallback = _first_text(sources, "deterministic_fallback_narration")
        if fallback:
            paragraphs.append(fallback)
        elif fallback_command:
            paragraphs.append(f"Your command is accepted: {fallback_command}.")

    plain_text = _dedupe_paragraphs(paragraphs)
    return {
        "format_version": _FORMAT_VERSION,
        "narration": narration if narration and not _equivalent(narration, line) else "",
        "messages": messages,
        "plain_text": plain_text,
        "npc": deepcopy(npc) if line else {},
    }


def visible_response_text(result: Any, fallback_command: str = "") -> str:
    return _text(build_visible_response(result, fallback_command).get("plain_text"))


def _iter_sources(value: Any) -> Iterable[dict[str, Any]]:
    root = _dict(value)
    if not root:
        return
    seen: set[int] = set()
    queue = [root]
    while queue:
        source = queue.pop(0)
        identity = id(source)
        if identity in seen:
            continue
        seen.add(identity)
        selected = _dict(source.get("first_call_visible_response"))
        visible = _dict(selected.get("visible_response")) or _dict(source.get("visible_response"))
        if selected:
            yield selected
        if visible:
            yield visible
        yield source
        for key in ("result", "resolved_result", "authoritative", "turn_contract", "narration_brief"):
            nested = _dict(source.get(key))
            if nested:
                queue.append(nested)


def _first_npc(sources: list[dict[str, Any]]) -> dict[str, Any]:
    for source in sources:
        npc = _dict(source.get("npc"))
        if _text(npc.get("line") or npc.get("text") or npc.get("content")):
            return npc
    return {}


def _first_text(sources: list[dict[str, Any]], *keys: str) -> str:
    for source in sources:
        for key in keys:
            value = _text(source.get(key))
            if value:
                return value
    return ""


def _dedupe_paragraphs(paragraphs: Iterable[str]) -> str:
    out: list[str] = []
    seen: set[str] = set()
    for raw in paragraphs:
        paragraph = _text(raw)
        if not paragraph:
            continue
        key = _normalize(paragraph)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(paragraph)
    return "\n\n".join(out)


def _normalize_dialogue_quotes(text: str) -> str:
    value = _text(text)
    if len(value) >= 2 and value[0] in {'"', "'", "“", "‘"} and value[-1] in {'"', "'", "”", "’"}:
        value = value[1:-1].strip()
    return value.replace("“", '"').replace("”", '"').strip('"').strip()


def _equivalent(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return _normalize(left) == _normalize(right)


def _normalize(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _text(value).casefold()).strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
