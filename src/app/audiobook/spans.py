"""Deterministic, lossless structural spans; unfamiliar punctuation stays source text."""
from __future__ import annotations

from typing import Protocol

from .hashing import text_hash
from .models import SourceSpan


DETECTOR_VERSION = "audiobook-spans-v1"
_OPEN_TO_CLOSE = {'"': '"', '“': '”', '«': '»', '「': '」', '『': '』', '‘': '’'}


class SpanDetector(Protocol):
    version: str

    def detect(self, chapter_id: str, text: str) -> tuple[SourceSpan, ...]: ...


class UnicodeDialogueDetector:
    version = DETECTOR_VERSION

    def detect(self, chapter_id: str, text: str) -> tuple[SourceSpan, ...]:
        if not text:
            return ()
        boundaries: list[tuple[int, int, str]] = []
        cursor = 0
        while cursor < len(text):
            line_end = text.find("\n", cursor)
            line_end = len(text) if line_end < 0 else line_end + 1
            line = text[cursor:line_end]
            if line.lstrip().startswith(("—", "–")):
                boundaries.append((cursor, line_end, "dialogue"))
            else:
                boundaries.extend(self._line_ranges(text, cursor, line_end))
            cursor = line_end
        merged: list[tuple[int, int, str]] = []
        for start, end, kind in boundaries:
            if merged and merged[-1][1] == start and merged[-1][2] == kind:
                previous = merged[-1]
                merged[-1] = (previous[0], end, kind)
            else:
                merged.append((start, end, kind))
        return tuple(
            SourceSpan(
                id=f"ab:sp:{text_hash(f'{chapter_id}:{ordinal}:{start}:{end}:{text[start:end]}')}",
                chapter_id=chapter_id,
                ordinal=ordinal,
                start_offset=start,
                end_offset=end,
                source_text=text[start:end],
                source_hash=text_hash(text[start:end]),
                structural_kind=kind,
                detector_version=self.version,
            )
            for ordinal, (start, end, kind) in enumerate(merged)
        )

    @staticmethod
    def _line_ranges(text: str, start: int, end: int) -> list[tuple[int, int, str]]:
        ranges: list[tuple[int, int, str]] = []
        cursor = start
        index = start
        while index < end:
            char = text[index]
            if char not in _OPEN_TO_CLOSE:
                index += 1
                continue
            if char == '‘' and index > start and text[index - 1].isalnum():
                index += 1
                continue
            closing = _OPEN_TO_CLOSE[char]
            finish = text.find(closing, index + 1, end)
            if finish < 0:
                index += 1
                continue
            if char == '‘' and finish + 1 < end and text[finish + 1].isalnum():
                index += 1
                continue
            if index > cursor:
                ranges.append((cursor, index, "narration"))
            ranges.append((index, finish + 1, "dialogue"))
            cursor = finish + 1
            index = cursor
        if cursor < end:
            ranges.append((cursor, end, "narration"))
        return ranges
