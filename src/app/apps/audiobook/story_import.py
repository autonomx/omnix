"""A story handed over from Storyteller (Storyteller roadmap ST-4.4).

Storyteller's pages are written as blocks, each spoken line already tagged with its speaker from the story's
cast. The story comes here as the writer's own text (the browser carries it, as it would a file), becomes a
Markdown source (a heading per chapter, a paragraph per block) and its cast becomes the project's speakers.
Its spoken lines are kept with the source, in order, so speaker analysis attributes a dialogue span that
matches one to that line's speaker; only the spans with no line, or whose line's speaker is not in the cast,
go to the classifier.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .annotation import Speaker, SpeakerAlias, SpanAnnotation, resolve_speaker
from .extraction import is_chapter_heading
from .models import SourceSpan

STORY_LINES_CONTRACT = "audiobook-story-lines-v1"
_TEXT_MAX_CHARS = 2_000_000
_LOOKAHEAD = 6  # lines a span may skip ahead to: Audiobook's segmentation can differ from the story's blocks
_WORD = re.compile(r"\w+")


class StoryImportBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: Literal["narration", "dialogue"] = "narration"
    text: str = Field(max_length=100_000)
    # The cast member's name as the story shows it; none for narration.
    speaker: str | None = Field(default=None, max_length=120)
    # The story named a speaker its cast doesn't have.
    unverified: bool = False


class StoryImportChapter(BaseModel):
    title: str = Field(default="", max_length=200)
    blocks: list[StoryImportBlock] = Field(max_length=5_000)


class StoryImportSpeaker(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=120)
    aliases: list[str] = Field(default_factory=list, max_length=20)


class StoryImport(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    author: str = Field(default="", max_length=200)
    story_project_id: str = Field(min_length=1, max_length=80)
    story_version_id: str | None = Field(default=None, min_length=1, max_length=80)
    chapters: list[StoryImportChapter] = Field(min_length=1, max_length=500)
    cast: list[StoryImportSpeaker] = Field(default_factory=list, max_length=60)

    @model_validator(mode="after")
    def _bounded(self) -> StoryImport:
        if not any(block.text.strip() for chapter in self.chapters for block in chapter.blocks):
            raise ValueError("the story has no text")
        if sum(len(block.text) for chapter in self.chapters for block in chapter.blocks) > _TEXT_MAX_CHARS:
            raise ValueError("the story is too long to narrate in one book")
        return self


def _paragraph(text: str) -> str:
    """A block as one paragraph; a block can't open a chapter of its own."""
    return " ".join(text.split()).lstrip("#").strip()


def _chapter_paragraphs(blocks: Sequence[StoryImportBlock]) -> list[str]:
    """A chapter's paragraphs; one that would read as a chapter heading ("Chapter two was the hardest.") is
    joined to the paragraph before it, so the story's chapters are only its own. (A chapter's first paragraph
    has none before it, and can still open a chapter of its own.)"""
    joined: list[str] = []
    for text in (_paragraph(block.text) for block in blocks):
        if not text:
            continue
        if joined and is_chapter_heading(text):
            joined[-1] = f"{joined[-1]} {text}"
        else:
            joined.append(text)
    return joined


def story_markdown(story: StoryImport) -> str:
    """The source Audiobook reads: a level-one heading per chapter and a paragraph per block."""
    parts: list[str] = []
    for number, chapter in enumerate(story.chapters, start=1):
        title = " ".join(chapter.title.split()) or f"Chapter {number}"
        parts.append("\n\n".join([f"# {title}", *_chapter_paragraphs(chapter.blocks)]))
    return "\n\n".join(parts) + "\n"


def story_speaker_lines(story: StoryImport) -> list[dict[str, Any]]:
    """The story's spoken lines in reading order, each with the speaker it was written for."""
    return [
        {"text": _paragraph(block.text), "speaker": (block.speaker or "").strip(), "unverified": block.unverified}
        for chapter in story.chapters
        for block in chapter.blocks
        if block.kind == "dialogue" and _paragraph(block.text)
    ]


def _words(text: str) -> list[str]:
    return _WORD.findall(unicodedata.normalize("NFKC", text).casefold())


class StoryLineMatcher:
    """Walks the story's spoken lines in order as the source's dialogue spans are read.

    A span matches the line whose words contain the span's words, from where the last match ended: a line
    with two quotations is two spans, and a repeated short line ("Yes.") goes to the next speaker who says it.
    A later line is matched only from its start, so a stray word is not given to a line that merely contains it.
    """

    def __init__(self, lines: Sequence[Mapping[str, Any]]) -> None:
        self._lines = [(_words(str(line.get("text") or "")), line) for line in lines]
        self._line = 0
        self._word = 0

    def match(self, span_text: str) -> Mapping[str, Any] | None:
        words = _words(span_text)
        if not words:
            return None
        expected = self._line + (1 if self._word else 0)
        for index in range(self._line, min(self._line + _LOOKAHEAD, len(self._lines))):
            line_words, line = self._lines[index]
            if index == self._line and self._word:
                # The rest of the line the last span began.
                found = self._find(line_words, words, self._word, len(line_words))
            else:
                # A line is entered at its start: the next line by any span, a line further on only by the
                # whole line or by enough of it not to be a stray word ("no" in a quotation kept as narration).
                entered = index == expected or len(words) == len(line_words) or len(words) >= 2
                found = self._find(line_words, words, 0, 1) if entered else None
            if found is not None:
                self._line, self._word = index, found + len(words)
                return line
        return None

    @staticmethod
    def _find(line_words: list[str], words: list[str], start: int, stop: int) -> int | None:
        for at in range(start, min(stop, len(line_words) - len(words) + 1)):
            if line_words[at:at + len(words)] == words:
                return at
        return None


def story_annotations(
    spans: Sequence[SourceSpan], matcher: StoryLineMatcher, *,
    speakers: Sequence[Speaker], aliases: Sequence[SpeakerAlias],
    dialogue_target_ids: set[str] | None,
) -> dict[str, SpanAnnotation]:
    """The dialogue spans the story already attributes, by span id.

    A span whose line names a speaker in the project's cast (an active speaker or a confirmed alias) is
    that speaker's; one whose line is unverified or names nobody in the cast is left to the classifier.
    """
    confirmed = [alias for alias in aliases if alias.status == "confirmed"]
    annotations: dict[str, SpanAnnotation] = {}
    for span in spans:
        if span.structural_kind != "dialogue":
            continue
        if dialogue_target_ids is not None and span.id not in dialogue_target_ids:
            continue
        line = matcher.match(span.source_text)
        if line is None or line.get("unverified") or not line.get("speaker"):
            continue
        speaker_id = resolve_speaker(str(line["speaker"]), speakers, confirmed)
        if speaker_id is None:
            continue
        annotations[span.id] = SpanAnnotation(
            span.id, "dialogue", speaker_id, None, "", None,
            {
                "semantic_authority": "story_handoff",
                "speaker_source": "story",
                "story_lines_contract": STORY_LINES_CONTRACT,
                "confidence": 1.0,
            },
            1.0,
        )
    return annotations
