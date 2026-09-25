"""Independent audit for speech cues left inside narration spans.

The span detector owns boundaries. This audit cannot change canonical text or
claim that a passage is dialogue; it only prevents suspicious text from being
silently approved as narration.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from typing import Any

from .models import SourceSpan


AUDIT_VERSION = "audiobook-dialogue-coverage-v1"
_QUOTE_MARKS = frozenset('"\'«»‹›「」『』„“‚‘’‟')
_DASH_LINE = re.compile(r"(?m)^[ \t]*[-–—―][ \t]+(?=\S)")
_SPEECH_TAG = re.compile(
    r"\b(?:said|asked|replied|answered|shouted|yelled|whispered|"
    r"muttered|murmured|cried|called|snapped|growled|hissed|"
    r"exclaimed|responded)\b",
    re.IGNORECASE,
)


def _quote_offset(text: str) -> int | None:
    for index, char in enumerate(text):
        if char not in _QUOTE_MARKS and unicodedata.category(char) not in {"Pi", "Pf"}:
            continue
        if char in {"'", "’"} and index > 0 and text[index - 1].isalnum():
            continue

        line_start = text.rfind("\n", 0, index) + 1
        prefix = text[line_start:index]
        nearby_prefix = prefix[-120:]
        if not prefix.strip():
            return index
        if _SPEECH_TAG.search(nearby_prefix):
            return index
        stripped = prefix.rstrip()
        if stripped.endswith((".", "!", "?", ":", "—", "–")):
            return index
    return None


def audit_dialogue_coverage(spans: Sequence[SourceSpan]) -> dict[str, dict[str, Any]]:
    """Return review evidence for narration that still contains speech cues.

    Quote punctuation and line-leading dialogue dashes are scanned separately
    from the detector. Speech tags are a weaker cue, so they trigger review only
    in chapters with no detected dialogue and substantial text.
    """
    findings: dict[str, dict[str, Any]] = {}
    by_chapter: dict[str, list[SourceSpan]] = {}
    for span in spans:
        by_chapter.setdefault(span.chapter_id, []).append(span)

    for chapter_spans in by_chapter.values():
        has_dialogue = any(span.structural_kind == "dialogue" for span in chapter_spans)
        chapter_chars = sum(len(span.source_text) for span in chapter_spans)
        for span in chapter_spans:
            if span.structural_kind != "narration":
                continue
            quote = _quote_offset(span.source_text)
            dash = _DASH_LINE.search(span.source_text)
            tag = (
                _SPEECH_TAG.search(span.source_text)
                if not has_dialogue and chapter_chars >= 2_000 else None
            )
            if quote is not None:
                signal, index = "quote_in_narration", quote
            elif dash is not None:
                signal, index = "dialogue_dash_in_narration", dash.start()
            elif tag is not None:
                signal, index = "speech_tag_without_dialogue", tag.start()
            else:
                continue
            findings[span.id] = {
                "audit_version": AUDIT_VERSION,
                "signal": signal,
                "source_offset": span.start_offset + index,
                "excerpt": span.source_text[max(0, index - 40):index + 120],
            }
    return findings
