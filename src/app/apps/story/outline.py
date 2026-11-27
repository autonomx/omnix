"""A story's plan as the model proposes it, and the deterministic check of it (ST-5.1).

The planning job asks for chapters, each a title and a few beats. The reply is a proposal: this
module cleans and caps it, and what it keeps is stored as the outline the writer edits. Its text is
material for the story, never an instruction.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.providers.structured import StructuredContract, StructuredRetryBudget, StructuredSemanticError

from .contracts import BEAT_MAX_CHARS, OUTLINE_BEATS_MAX, OUTLINE_CHAPTERS_MAX, TITLE_MAX_CHARS
from .page_contract import clean_line

#: Chapters a plan asks for when the writer names no number.
DEFAULT_CHAPTERS = 5
#: A plan the model writes is held to this; the writer's own outline may be longer.
PLANNED_CHAPTERS_MAX = 20
PLANNED_BEATS_MAX = 8


class OutlineChapterReply(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = ""
    beats: list[str] = Field(default_factory=list)


class StoryOutlineReply(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chapters: list[OutlineChapterReply] = Field(min_length=1)


def _has_beats(reply: StoryOutlineReply) -> None:
    if not any(beat.strip() for chapter in reply.chapters for beat in chapter.beats):
        raise StructuredSemanticError("story outline has no beats")


STORY_OUTLINE_CONTRACT: StructuredContract[StoryOutlineReply] = StructuredContract(
    contract_id="story.outline",
    version=1,
    output_model=StoryOutlineReply,
    semantic_validator=_has_beats,
    temperature=0.7,
    max_tokens=4_096,
    thinking=False,
)

STORY_OUTLINE_BUDGET = StructuredRetryBudget(
    max_provider_calls=3,
    max_transport_retries=1,
    max_format_downgrades=1,
    max_validation_regenerations=1,
    deadline_seconds=120.0,
)


def check_outline(reply: StoryOutlineReply) -> list[dict[str, Any]]:
    """The chapters the reply plans, cleaned and capped; a chapter with no beat is left out."""
    chapters: list[dict[str, Any]] = []
    limit = min(PLANNED_CHAPTERS_MAX, OUTLINE_CHAPTERS_MAX)
    for item in reply.chapters:
        if len(chapters) >= limit:
            break
        beats = [text for text in (clean_line(beat, BEAT_MAX_CHARS) for beat in item.beats) if text]
        if not beats:
            continue
        chapters.append({"title": clean_line(item.title, TITLE_MAX_CHARS),
                         "beats": [{"text": text} for text in beats[:min(PLANNED_BEATS_MAX, OUTLINE_BEATS_MAX)]]})
    return chapters


def outline_text(chapters: list[dict[str, Any]]) -> str:
    """The plan as Markdown, for the job's output."""
    parts = []
    for number, chapter in enumerate(chapters, start=1):
        heading = f"## Chapter {number}" + (f": {chapter['title']}" if chapter.get("title") else "")
        parts.append("\n".join([heading, *(f"- {beat['text']}" for beat in chapter.get("beats") or [])]))
    return "\n\n".join(parts)
