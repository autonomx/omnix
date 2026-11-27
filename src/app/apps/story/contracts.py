"""The storyteller's project API: a story with its pages, moves, versions, cast and notes (ST-1.2)."""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

StoryMode = Literal["writing", "interactive"]
OriginKind = Literal["new", "asset", "job", "local"]
VersionKind = Literal["rewrite", "expand", "dialogue", "summarize", "kept_run", "manual"]
NoteKind = Literal["world", "preset"]

TITLE_MAX_CHARS = 200
TEXT_MAX_CHARS = 400_000
BLOCKS_MAX = 2_000
CHARACTERS_MAX = 60
NOTES_MAX = 100
IMPORT_MAX = 200
OUTLINE_CHAPTERS_MAX = 40
OUTLINE_BEATS_MAX = 12
BEAT_MAX_CHARS = 600
# Control characters other than tab and newline: not text, and not allowed in an EPUB or DOCX (ST-6.5).
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class StoryBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: Literal["narration", "dialogue"] = "narration"
    text: str = Field(max_length=TEXT_MAX_CHARS)
    speaker_id: str | None = Field(default=None, max_length=80)
    # "unverified" when the model named a speaker the cast doesn't have (ST-2.2).
    attribution: str | None = Field(default=None, max_length=40)

    @field_validator("text")
    @classmethod
    def _without_control_characters(cls, value: str) -> str:
        return CONTROL_CHARS.sub("", value)


class StoryPage(BaseModel):
    id: str
    chapter: int
    position: int
    title: str
    blocks: list[StoryBlock]
    # Next moves the model offered the player with this page (ST-2.1, ST-3.2).
    suggested_moves: list[str] = Field(default_factory=list)
    hidden: bool
    source_job_id: str | None = None
    # The page this one continued from; the visible run is one chain of them (ST-3.4).
    parent_page_id: str | None = None
    created_at: str


class StoryMove(BaseModel):
    id: str
    page_id: str | None = None
    player_text: str
    chosen_suggestion: str = ""
    parent_move_id: str | None = None
    created_at: str


class StoryVersionPage(BaseModel):
    chapter: int = 1
    title: str = ""
    blocks: list[StoryBlock] = Field(default_factory=list, max_length=BLOCKS_MAX)


class StorySelection(BaseModel):
    """A change a job proposes to blocks ``[start, end)`` of one page, for the writer to accept or reject (ST-6.2)."""

    page_id: str
    start: int
    end: int
    original: list[StoryBlock]
    proposed: list[StoryBlock]
    status: Literal["pending", "accepted", "rejected"]


class StoryVersionSummary(BaseModel):
    id: str
    version_number: int
    kind: VersionKind
    title: str
    source_job_id: str | None = None
    created_at: str
    # Set when the version proposes a change to a selection rather than reworking the whole manuscript.
    selection: StorySelection | None = None


class StoryVersion(StoryVersionSummary):
    pages: list[StoryVersionPage]


class StoryCharacter(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")
    name: str = Field(min_length=1, max_length=120)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    description: str = Field(default="", max_length=2_000)
    traits: list[str] = Field(default_factory=list, max_length=20)
    role: str = Field(default="", max_length=120)
    # A character a page proposed that the writer hasn't accepted yet (ST-2.3).
    suggested: bool = False


class StoryNoteInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = Field(default=None, max_length=80)
    kind: NoteKind = "world"
    title: str = Field(default="", max_length=TITLE_MAX_CHARS)
    body: str = Field(default="", max_length=20_000)
    # A preset's tone and writing style; its body holds its instructions (ST-5.2).
    tone: str = Field(default="", max_length=80)
    writing_style: str = Field(default="", max_length=80)


class StoryNote(BaseModel):
    id: str
    kind: NoteKind
    title: str
    body: str
    tone: str = ""
    writing_style: str = ""
    created_at: str
    updated_at: str


# -- the plan (ST-5.1) ----------------------------------------------------------------------------


class StoryOutlineBeat(BaseModel):
    id: str
    text: str
    # The page this beat was drafted into, once it has been.
    page_id: str | None = None


class StoryOutlineChapter(BaseModel):
    chapter: int
    title: str = ""
    beats: list[StoryOutlineBeat] = Field(default_factory=list)


class StoryOutlineBeatInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # A beat the outline has keeps its id (and the page drafted from it); any other is a new beat.
    id: str | None = Field(default=None, max_length=80)
    text: str = Field(min_length=1, max_length=BEAT_MAX_CHARS)


class StoryOutlineChapterInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(default="", max_length=TITLE_MAX_CHARS)
    beats: list[StoryOutlineBeatInput] = Field(default_factory=list, max_length=OUTLINE_BEATS_MAX)


class StoryOutlineReplace(BaseModel):
    """The writer's plan, chapter by chapter in order: a chapter's number is its place in the list."""

    chapters: list[StoryOutlineChapterInput] = Field(default_factory=list, max_length=OUTLINE_CHAPTERS_MAX)


class StoryProjectSummary(BaseModel):
    id: str
    title: str
    premise: str
    mode: StoryMode
    tone: str
    writing_style: str
    origin_kind: OriginKind
    origin_ref: str
    page_count: int = 0
    word_count: int = 0
    deleted_at: str | None = None
    created_at: str
    updated_at: str


class StoryProject(StoryProjectSummary):
    read_settings: dict[str, Any] = Field(default_factory=dict)
    outline: list[StoryOutlineChapter] = Field(default_factory=list)
    # The preset the story is written with ('' for none, ST-5.2).
    preset_id: str = ""
    pages: list[StoryPage] = Field(default_factory=list)
    moves: list[StoryMove] = Field(default_factory=list)
    versions: list[StoryVersionSummary] = Field(default_factory=list)
    characters: list[StoryCharacter] = Field(default_factory=list)
    notes: list[StoryNote] = Field(default_factory=list)


class StoryProjectList(BaseModel):
    projects: list[StoryProjectSummary]


class StoryProjectCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(default="", max_length=TITLE_MAX_CHARS)
    premise: str = Field(default="", max_length=500)
    mode: StoryMode = "writing"
    tone: str = Field(default="", max_length=80)
    writing_style: str = Field(default="", max_length=80)
    read_settings: dict[str, Any] = Field(default_factory=dict)


class StoryProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str | None = Field(default=None, max_length=TITLE_MAX_CHARS)
    premise: str | None = Field(default=None, max_length=500)
    mode: StoryMode | None = None
    tone: str | None = Field(default=None, max_length=80)
    writing_style: str | None = Field(default=None, max_length=80)
    read_settings: dict[str, Any] | None = None
    # A preset note of this project to write with ('' for none); its tone and style become the story's.
    preset_id: str | None = Field(default=None, max_length=80)


class StoryPageCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chapter: int | None = Field(default=None, ge=1, le=10_000)
    title: str = Field(default="", max_length=TITLE_MAX_CHARS)
    blocks: list[StoryBlock] = Field(min_length=1, max_length=BLOCKS_MAX)


class StoryPageUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str | None = Field(default=None, max_length=TITLE_MAX_CHARS)
    blocks: list[StoryBlock] | None = Field(default=None, min_length=1, max_length=BLOCKS_MAX)
    # The blocks the writer started from: the edit is refused when the page has changed since (ST-6.1).
    base_blocks: list[StoryBlock] | None = Field(default=None, max_length=BLOCKS_MAX)

    @model_validator(mode="after")
    def _an_edit_names_its_base_and_keeps_text(self) -> StoryPageUpdate:
        if self.blocks is not None:
            if self.base_blocks is None:
                raise ValueError("an edit of a page's blocks names the blocks it started from")
            if not any(block.text.strip() for block in self.blocks):
                raise ValueError("a page needs at least one paragraph")
        return self


class StoryVersionCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(default="", max_length=TITLE_MAX_CHARS)
    # kept_run: "Keep this run" keeps an interactive run as a finished story (ST-3.6).
    kind: Literal["manual", "kept_run"] = "manual"


class StoryCharactersReplace(BaseModel):
    characters: list[StoryCharacter] = Field(default_factory=list, max_length=CHARACTERS_MAX)


class StoryNotesReplace(BaseModel):
    notes: list[StoryNoteInput] = Field(default_factory=list, max_length=NOTES_MAX)


class StoryImportItem(BaseModel):
    """One story the browser knows about: a saved asset, an old job's output or its local draft (ST-1.4)."""

    model_config = ConfigDict(extra="ignore")

    origin_kind: Literal["asset", "job", "local"]
    origin_ref: str = Field(min_length=1, max_length=200)
    title: str = Field(default="", max_length=TITLE_MAX_CHARS)
    premise: str = Field(default="", max_length=20_000)
    mode: StoryMode = "writing"
    text: str = Field(default="", max_length=TEXT_MAX_CHARS)
    characters: list[StoryCharacter] = Field(default_factory=list, max_length=CHARACTERS_MAX)
    # A story the browser had in its trash arrives in the server's trash, so it can still be restored.
    trashed: bool = False


class StoryImportRequest(BaseModel):
    items: list[StoryImportItem] = Field(default_factory=list, max_length=IMPORT_MAX)


class StoryImportResult(BaseModel):
    created: list[str]
    existing: list[str]


class StoryDeleted(BaseModel):
    id: str
    deleted: bool = True


# -- voices (ST-4.2) ------------------------------------------------------------------------------


class StoryCastVoice(BaseModel):
    """Who speaks in a story and in which voice: the narrator, then each character."""

    speaker_id: str
    name: str
    voice_id: str = ""
    voice_revision: str = ""
    # auto (matched to the character's description) or writer (the writer's choice, which wins).
    chosen_by: str = ""


class StoryVoiceOption(BaseModel):
    voice_id: str
    name: str
    description: str = ""


class StoryVoiceCast(BaseModel):
    project_id: str
    cast: list[StoryCastVoice]
    voices: list[StoryVoiceOption]


class StoryVoiceChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice_id: str = Field(min_length=1, max_length=200)


class StorySpeechPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: str = Field(min_length=1, max_length=80)


class StorySpeechSegment(BaseModel):
    """One block of a page as it is spoken: its voice, and its text sentence by sentence."""

    block_index: int
    speaker_id: str
    voice_id: str
    sentences: list[str]
    # The block's speaker isn't in the cast (or has no voice): spoken in a neutral voice, and flagged.
    unknown_speaker: bool = False


class StorySpeechPlan(BaseModel):
    project_id: str
    page_id: str
    segments: list[StorySpeechSegment]


class StorySpeechSentence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: str = Field(min_length=1, max_length=80)
    # "" for a line whose speaker is not known.
    speaker_id: str = Field(default="narrator", max_length=80)
    # One sentence of a speech plan, no more (platform voice SENTENCE_MAX_CHARS).
    text: str = Field(min_length=1, max_length=300)
