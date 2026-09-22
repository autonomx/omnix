"""Deterministic, lossless structural spans; unfamiliar punctuation stays source text."""
from __future__ import annotations

import re
from typing import Protocol

from .hashing import text_hash
from .models import SourceSpan


DETECTOR_VERSION = "audiobook-spans-v3"
_OPEN_TO_CLOSE = {'"': '"', '“': '”', '«': '»', '「': '」', '『': '』', '‘': '’'}
_SPEECH_TAG_VERBS = (
    "said", "asked", "replied", "answered", "shouted", "yelled", "whispered",
    "muttered", "murmured", "cried", "called", "snapped", "growled", "hissed",
    "sighed", "added", "continued", "insisted", "warned", "ordered", "demanded",
    "exclaimed", "remarked", "responded",
)
_DASH_ATTRIBUTION = re.compile(
    r",\s*(?:(?:[A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*){0,2})|he|she|they|"
    r"the\s+[\w'-]+)\s+(?:"
    + "|".join(re.escape(item) for item in _SPEECH_TAG_VERBS)
    + r")\b",
    re.IGNORECASE,
)


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
                boundaries.extend(self._dash_line_ranges(text, cursor, line_end))
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
    def _dash_line_ranges(text: str, start: int, end: int) -> list[tuple[int, int, str]]:
        """Keep em-dash dialogue lossless while separating obvious speech tags.

        A line such as "— Don't move, Daniel said, raising his hand." should not
        make the narrator clause use Daniel's character voice. Ambiguous dash
        lines remain one dialogue span and can be reviewed by the classifier.
        """
        line = text[start:end]
        match = _DASH_ATTRIBUTION.search(line)
        if match is None:
            return [(start, end, "dialogue")]
        # Keep the punctuation terminating the spoken phrase with the dialogue.
        split = start + match.start() + 1
        if split <= start or split >= end:
            return [(start, end, "dialogue")]
        return [(start, split, "dialogue"), (split, end, "narration")]

    @staticmethod
    def _line_ranges(text: str, start: int, end: int) -> list[tuple[int, int, str]]:
        # In conventional multi-paragraph dialogue, each continued paragraph
        # opens with a quote but only the final paragraph closes it. Treat an
        # unmatched opening quote at the start of a line as dialogue rather
        # than silently handing that paragraph to the narrator.
        first = start
        while first < end and text[first] in {" ", "\t"}:
            first += 1
        if first < end and text[first] in _OPEN_TO_CLOSE:
            opening = text[first]
            closing = _OPEN_TO_CLOSE[opening]
            if text.find(closing, first + 1, end) < 0:
                return [(start, end, "dialogue")]

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
