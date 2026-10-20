"""Translating a dub, line by line, to fit the time each line took (Voice Studio Phase 6).

The LLM sees a batch of lines with the lines around them for context, and each
line's time budget as a character budget (speech runs at about
``CHARS_PER_SECOND``). It answers one JSON object; a translation is a proposal
until a person approves it in review. A local model (the default) waits on the
``llm-local`` device permits; a cloud model sends the transcript off the
machine, which the review screen says before it is chosen.
"""
from __future__ import annotations

import json
import re
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any

BATCH_SIZE = 8
CONTEXT_LINES = 2
# Spoken characters per second; translations are asked to stay near budget * this.
CHARS_PER_SECOND = 14.0
LOCAL_PROVIDERS = frozenset({"lmstudio", "llamacpp"})
LANGUAGE_NAMES = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German", "it": "Italian", "pt": "Portuguese",
    "nl": "Dutch", "pl": "Polish", "ru": "Russian", "uk": "Ukrainian", "ja": "Japanese", "zh": "Chinese",
    "ko": "Korean", "sv": "Swedish", "da": "Danish", "fi": "Finnish", "cs": "Czech", "el": "Greek",
}


class TranslationError(RuntimeError):
    """The model's answer could not be used."""


@dataclass(frozen=True)
class LineToTranslate:
    id: str
    speaker: str
    text: str
    budget_seconds: float


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code.lower().split("-")[0], code)


def character_budget(seconds: float) -> int:
    return max(4, int(round(seconds * CHARS_PER_SECOND)))


def _parse_object(content: str) -> dict[str, Any]:
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise TranslationError("the model did not answer with a JSON object")
    try:
        value = json.loads(text[start:end + 1])
    except ValueError as exc:
        raise TranslationError(f"the model's JSON could not be read: {exc}") from exc
    if not isinstance(value, dict):
        raise TranslationError("the model did not answer with a JSON object")
    return value


def batch_messages(lines: list[LineToTranslate], *, before: list[str], after: list[str],
                   source: str, target: str) -> list[dict[str, str]]:
    request = {
        "source_language": language_name(source), "target_language": language_name(target),
        "context_before": before, "context_after": after,
        "lines": [{"id": line.id, "speaker": line.speaker, "text": line.text,
                   "seconds": round(line.budget_seconds, 2),
                   "max_characters": character_budget(line.budget_seconds)} for line in lines],
    }
    system = (
        "You translate film and video dialogue for dubbing. Translate each line naturally, as people "
        "speak, keeping its meaning, tone and register. A dubbed line must be speakable in the time the "
        "original took: keep each translation at or under its max_characters (shorter wording beats a "
        "literal one). Never merge, split, drop or reorder lines. Use the context lines only to "
        "understand the dialogue; do not translate them. Answer with one JSON object and nothing else: "
        '{"lines": [{"id": "<line id>", "translation": "<text>"}]}'
    )
    return [{"role": "system", "content": system},
            {"role": "user", "content": json.dumps(request, ensure_ascii=False)}]


def parse_batch(content: str, lines: list[LineToTranslate]) -> dict[str, str]:
    value = _parse_object(content)
    entries = value.get("lines")
    if not isinstance(entries, list):
        raise TranslationError('the answer has no "lines" list')
    wanted = {line.id for line in lines}
    found: dict[str, str] = {}
    for entry in entries:
        if isinstance(entry, dict) and str(entry.get("id")) in wanted:
            text = " ".join(str(entry.get("translation") or "").split())
            if text:
                found[str(entry["id"])] = text
    missing = wanted - set(found)
    if missing:
        raise TranslationError(f"the answer left out {len(missing)} line(s)")
    return found


def shorten_messages(line: LineToTranslate, current: str, *, target: str, took_seconds: float) -> list[dict[str, str]]:
    request = {"language": language_name(target), "source_line": line.text, "translation": current,
               "spoken_seconds": round(took_seconds, 2), "allowed_seconds": round(line.budget_seconds, 2),
               "max_characters": character_budget(line.budget_seconds * 0.9)}
    system = (
        "You shorten dubbing lines. The translation takes too long to say. Rewrite it in the same language "
        "so it keeps the meaning and fits max_characters, using shorter words or dropping filler. Answer "
        'with one JSON object and nothing else: {"translation": "<text>"}'
    )
    return [{"role": "system", "content": system},
            {"role": "user", "content": json.dumps(request, ensure_ascii=False)}]


def parse_shortened(content: str) -> str:
    text = " ".join(str(_parse_object(content).get("translation") or "").split())
    if not text:
        raise TranslationError("the shortened translation is empty")
    return text


class Translator:
    """One chat model, called with the device permit a local model needs."""

    def __init__(self, provider_name: str = "") -> None:
        self.provider_name = provider_name.strip()

    def _provider(self) -> Any:
        from app.providers.service import get_provider

        provider = get_provider(self.provider_name or None)
        if provider is None:
            raise TranslationError("no language model is configured for translation")
        return provider

    def is_local(self) -> bool:
        provider = self._provider()
        name = str(getattr(provider, "provider_name", "") or self.provider_name).casefold().removeprefix("llm:")
        return name in LOCAL_PROVIDERS

    def chat(self, messages: list[dict[str, str]]) -> str:
        from app.persistence.device_permits import device_permit_slot
        from app.providers import ChatMessage

        provider = self._provider()
        name = str(getattr(provider, "provider_name", "") or self.provider_name).casefold().removeprefix("llm:")
        permit = device_permit_slot("llm-local", priority="batch") if name in LOCAL_PROVIDERS else nullcontext()
        with permit:
            response = provider.chat_completion(messages=[ChatMessage(role=item["role"], content=item["content"])
                                                          for item in messages])
        return str(getattr(response, "content", "") or "")

    def translate(self, lines: list[LineToTranslate], *, before: list[str], after: list[str],
                  source: str, target: str) -> dict[str, str]:
        """Translations by line id; one retry when the answer is unusable."""
        messages = batch_messages(lines, before=before, after=after, source=source, target=target)
        try:
            return parse_batch(self.chat(messages), lines)
        except TranslationError:
            return parse_batch(self.chat(messages), lines)

    def shorten(self, line: LineToTranslate, current: str, *, target: str, took_seconds: float) -> str:
        return parse_shortened(self.chat(shorten_messages(line, current, target=target, took_seconds=took_seconds)))


__all__ = [
    "BATCH_SIZE",
    "CHARS_PER_SECOND",
    "CONTEXT_LINES",
    "LineToTranslate",
    "TranslationError",
    "Translator",
    "batch_messages",
    "character_budget",
    "language_name",
    "parse_batch",
    "parse_shortened",
    "shorten_messages",
]
