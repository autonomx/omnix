"""Voice Studio script grammar, shared with ``web/src/features/voice/scriptLines.ts``.

- ``name: text`` lines speak as ``name`` (names are at most 50 characters).
- Untagged lines join into one Narrator segment, as before.
- ``{pause 600ms}`` or ``{pause 1.5s}`` inserts silence before the next segment.
  Braces, because Fish S2 Pro reads square brackets as delivery instructions.
  A pause token on its own line, at the start of a line, or inside a line all
  work; inside a line it splits the line into two segments of the same speaker.
- Blank lines are ignored, as before.

Both parsers run the same vectors (``scriptGrammar.vectors.json`` in the web
feature folder), so the segments a script previews as are the ones it renders.
"""
from __future__ import annotations

import re
from typing import Any

DEFAULT_UNTAGGED_SPEAKER = "Narrator"
MAX_SPEAKER_NAME = 50
MAX_PAUSE_MS = 10_000

_LINES = re.compile(r"\r\n|\n|\r")
_PAUSE = re.compile(r"\{\s*pause\s+(\d+(?:\.\d+)?)\s*(ms|s)\s*\}", re.IGNORECASE)


def _pause_ms(match: re.Match[str]) -> int:
    value = float(match.group(1))
    milliseconds = value if match.group(2).lower() == "ms" else value * 1000
    return int(min(MAX_PAUSE_MS, max(0, round(milliseconds))))


def _tagged(line: str) -> tuple[str, str] | None:
    colon = line.find(":")
    if colon <= 0:
        return None
    speaker = line[:colon].strip()
    content = line[colon + 1:].strip()
    if not speaker or not content or len(speaker) > MAX_SPEAKER_NAME:
        return None
    return speaker, content


def parse_script(text: str) -> list[dict[str, Any]]:
    """Segments ``{index, speaker, text}``, plus ``pause_before_ms`` after a pause token."""
    segments: list[dict[str, Any]] = []
    untagged: list[str] = []
    pending_pause = 0

    def emit(speaker: str, content: str) -> None:
        nonlocal pending_pause
        content = content.strip()
        if not content:
            return
        segment: dict[str, Any] = {"index": len(segments), "speaker": speaker, "text": content}
        if pending_pause and segments:
            segment["pause_before_ms"] = pending_pause
        pending_pause = 0
        segments.append(segment)

    def flush_untagged() -> None:
        if untagged:
            emit(DEFAULT_UNTAGGED_SPEAKER, " ".join(untagged))
            untagged.clear()

    for raw_line in _LINES.split(text):
        line = raw_line.strip()
        if not line:
            continue
        # Leading pause tokens belong before whatever the line says.
        leading = _PAUSE.match(line)
        while leading:
            flush_untagged()
            pending_pause = min(MAX_PAUSE_MS, pending_pause + _pause_ms(leading))
            line = line[leading.end():].strip()
            leading = _PAUSE.match(line)
        if not line:
            continue
        tagged = _tagged(line)
        speaker = tagged[0] if tagged else None
        content = tagged[1] if tagged else line
        if speaker is not None:
            flush_untagged()
        position = 0
        for match in _PAUSE.finditer(content):
            part = content[position:match.start()].strip()
            if speaker is None:
                if part:
                    untagged.append(part)
                flush_untagged()
            else:
                emit(speaker, part)
            pending_pause = min(MAX_PAUSE_MS, pending_pause + _pause_ms(match))
            position = match.end()
        rest = content[position:].strip()
        if speaker is None:
            if rest:
                untagged.append(rest)
        else:
            emit(speaker, rest)
    flush_untagged()
    return segments


def script_speakers(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for segment in segments:
        speaker = str(segment.get("speaker") or DEFAULT_UNTAGGED_SPEAKER)
        counts[speaker] = counts.get(speaker, 0) + 1
    return [{"name": speaker, "count": count} for speaker, count in counts.items()]


__all__ = ["DEFAULT_UNTAGGED_SPEAKER", "MAX_PAUSE_MS", "parse_script", "script_speakers"]
