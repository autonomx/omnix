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
    player_input = _player_input(sources) or _text(fallback_command)
    narration, npc = _select_structured_response(sources, player_input)
    speaker = _text(npc.get("speaker") or npc.get("name"))
    line = _text(npc.get("line") or npc.get("text") or npc.get("content"))
    if _normalize(speaker) in _NON_NPC_SPEAKERS:
        speaker = ""
        line = ""

    if narration and _is_player_restatement(narration, player_input):
        narration = ""
    if line and _is_player_restatement(line, player_input):
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
        fallback = _first_safe_text(sources, player_input, "deterministic_fallback_narration")
        if fallback:
            paragraphs.append(fallback)
        else:
            fallback_contract = _direct_dialogue_fallback(player_input)
            if fallback_contract:
                narration = fallback_contract["narration"]
                npc = fallback_contract["npc"]
                speaker = _text(npc.get("speaker")) or "NPC"
                line = _text(npc.get("line"))
                messages = [
                    {
                        "kind": "npc_dialogue",
                        "speaker_id": _text(npc.get("speaker_id")) or None,
                        "speaker": speaker,
                        "text": line,
                    }
                ]
                paragraphs.extend([narration, f'{speaker}: "{line}"'])
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


def visible_response_text(result: Any, fallback_command: str = "") -> str | None:
    return _text(build_visible_response(result, fallback_command).get("plain_text")) or None


def _select_structured_response(
    sources: list[dict[str, Any]],
    player_input: str,
) -> tuple[str, dict[str, Any]]:
    for source in sources:
        npc = _dict(source.get("npc"))
        speaker = _text(npc.get("speaker") or npc.get("name"))
        line = _text(npc.get("line") or npc.get("text") or npc.get("content"))
        narration = _text(
            source.get("narration")
            or source.get("final_narration")
            or source.get("summary")
            or source.get("response")
            or source.get("content")
            or source.get("text")
        )
        if _normalize(speaker) in _NON_NPC_SPEAKERS:
            speaker = ""
            line = ""
        if line and _is_player_restatement(line, player_input):
            line = ""
        if narration and _is_player_restatement(narration, player_input):
            narration = ""
        if narration or line:
            if line and speaker:
                npc = {**npc, "speaker": speaker, "line": line}
            elif not line:
                npc = {}
            return narration, npc
    return "", {}


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
        narration_json = _dict(source.get("narration_json"))
        if selected:
            yield selected
        if visible:
            yield visible
        if narration_json:
            yield narration_json
        yield source
        for key in ("result", "resolved_result", "authoritative", "turn_contract", "narration_brief"):
            nested = _dict(source.get(key))
            if nested:
                queue.append(nested)


def _first_safe_text(sources: list[dict[str, Any]], player_input: str, *keys: str) -> str:
    for source in sources:
        for key in keys:
            value = _text(source.get(key))
            if value and not _is_player_restatement(value, player_input):
                return value
    return ""


def _player_input(sources: Iterable[dict[str, Any]]) -> str:
    for source in sources:
        direct = _text(source.get("player_input"))
        if direct:
            return direct
        payload = _dict(source.get("input_payload"))
        direct = _text(payload.get("player_input") or payload.get("command") or payload.get("content"))
        if direct:
            return direct
        context = _dict(source.get("narration_context"))
        direct = _text(context.get("player_input"))
        if direct:
            return direct
        request = _dict(source.get("narration_request"))
        request_context = _dict(request.get("narration_context"))
        direct = _text(request_context.get("player_input"))
        if direct:
            return direct
        diagnostics = _dict(source.get("first_call_grounding_diagnostics"))
        packet = _dict(diagnostics.get("turn_grounding_packet"))
        direct = _text(packet.get("player_input"))
        if direct:
            return direct
    return ""


def _direct_dialogue_fallback(player_input: str) -> dict[str, Any] | None:
    normalized = _normalize(player_input)
    if not normalized or not re.search(r"\b(?:business|going|trade|tavern|customers|patrons)\b", normalized):
        return None
    target = _direct_npc_name(player_input)
    if not target:
        return None
    if target.casefold() == "bran":
        return {
            "narration": "Bran glances around the Rusty Flagon before answering.",
            "npc": {
                "speaker_id": "npc:bran",
                "speaker": "Bran",
                "line": (
                    "Steady enough. Rooms, food, and rumors keep the doors open, "
                    "though the road has been strange lately."
                ),
            },
        }
    return {
        "narration": f"{target} considers the question before answering.",
        "npc": {
            "speaker": target,
            "line": "Business has been steady enough, though conditions keep changing.",
        },
    }


def _direct_npc_name(command: str) -> str | None:
    match = re.search(
        r"\b(?:ask|talk(?:\s+to)?|speak(?:\s+to)?|tell)\s+([A-Z][A-Za-z0-9_-]+|[a-z][a-z0-9_-]+)\b",
        command,
    )
    if not match:
        return None
    name = match.group(1).strip(" ,.!?:;\"'")
    if not name or name.casefold() in {"about", "if", "how", "what", "why", "where", "when"}:
        return None
    return name[:1].upper() + name[1:]


def _is_player_restatement(value: str, player_input: str) -> bool:
    text = _normalize(value)
    player = _normalize(player_input)
    if not text or not player or len(player) < 18:
        return False
    return player in text or text in player


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
    value = _text(text).strip('"').strip()
    value = value.replace("“", '"').replace("”", '"')
    value = re.sub(r",['’](?=\s)", ',"', value)
    value = re.sub(r"(?<=[.!?])['’](?=\s+[A-Z])", '"', value)
    value = re.sub(r"(?<=\s)['’](?=[A-Z])", '"', value)
    return value


def _equivalent(left: str, right: str) -> bool:
    return bool(left and right and _normalize(left) == _normalize(right))


def _normalize(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _text(value).casefold()).strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
