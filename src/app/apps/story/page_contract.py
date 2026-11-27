"""A story page as the model writes it, and the deterministic check of what it claims (ST-2.1, ST-2.2).

The model returns one page as tagged blocks. Its reply is a proposal: this module decides who speaks
each line. A speaker must be in the project's cast or among the characters this reply proposes;
any other is kept on its line as ``attribution: "unverified"``. Proposed characters are capped and
cleaned, and every text field stays data: nothing here is ever followed as an instruction.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.providers.structured import StructuredContract, StructuredRetryBudget, StructuredSemanticError

from .contracts import CHARACTERS_MAX

#: Characters one page may propose; more than this are dropped and their lines are unverified.
NEW_CHARACTERS_MAX = 4
SUGGESTED_MOVES_MAX = 3
PAGE_BLOCKS_MAX = 200
BLOCK_TEXT_MAX = 4_000
NAME_MAX = 80
DESCRIPTION_MAX = 400
MOVE_MAX = 200
TITLE_MAX = 200
#: The rolling summary of the story so far that an interactive page carries forward (ST-3.3).
SUMMARY_MAX = 1_500
ID_MAX = 40

UNVERIFIED = "unverified"


class PageBlockReply(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: Literal["narration", "dialogue"] = "narration"
    speaker_id: str | None = None
    text: str = ""


class NewCharacterReply(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str = ""
    description: str = ""


class StoryPageReply(BaseModel):
    """One page: never a whole story, so a reply is not cut off by its token limit."""

    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    blocks: list[PageBlockReply] = Field(min_length=1)
    new_characters: list[NewCharacterReply] = Field(default_factory=list)
    suggested_moves: list[str] = Field(default_factory=list)
    summary: str | None = None


def _has_text(reply: StoryPageReply) -> None:
    if not any(block.text.strip() for block in reply.blocks):
        raise StructuredSemanticError("story page has no text")


STORY_PAGE_CONTRACT: StructuredContract[StoryPageReply] = StructuredContract(
    contract_id="story.page",
    version=1,
    output_model=StoryPageReply,
    semantic_validator=_has_text,
    temperature=0.8,
    max_tokens=4_096,
    # Fiction gains nothing from a thinking pass, and it costs seconds on every page.
    thinking=False,
)

#: A cut-off or malformed reply is asked for again within this budget; it is never saved.
STORY_PAGE_BUDGET = StructuredRetryBudget(
    max_provider_calls=3,
    max_transport_retries=1,
    max_format_downgrades=1,
    max_validation_regenerations=1,
    deadline_seconds=180.0,
)


@dataclass(frozen=True, slots=True)
class CheckedPage:
    title: str | None
    blocks: list[dict[str, Any]]
    new_characters: list[dict[str, Any]] = field(default_factory=list)
    suggested_moves: list[str] = field(default_factory=list)
    summary: str = ""

    @property
    def unverified(self) -> int:
        return sum(1 for block in self.blocks if block.get("attribution") == UNVERIFIED)


_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_SPACES = re.compile(r"\s+")
_ID_CHARS = re.compile(r"[^a-z0-9_-]+")


def _clean_text(value: object, limit: int) -> str:
    """Paragraph text: control characters removed (line breaks kept), trimmed and capped."""
    return _CONTROL.sub("", str(value or "")).strip()[:limit].strip()


def _clean_line(value: object, limit: int) -> str:
    return _SPACES.sub(" ", _CONTROL.sub("", str(value or ""))).strip()[:limit].strip()


#: One line of model text, cleaned: for the other contracts of the story job (the outline).
clean_line = _clean_line


def _slug(value: object) -> str:
    return _ID_CHARS.sub("-", str(value or "").strip().lower()).strip("-")[:ID_MAX].strip("-")


def _key(value: object) -> str:
    return _clean_line(value, NAME_MAX).casefold()


_QUOTED = re.compile(r"\"[^\"]*\"|“[^”]*”")
_WORD = re.compile(r"\w")


def _spoken_parts(text: str) -> list[tuple[str, str]]:
    """A spoken line split into its quoted words and the narration around them (the dialogue tag).

    Only a line whose quotes all pair up is split, and only when words stand outside them; anything
    else stays one spoken line, as written.
    """
    if text.count('"') % 2 or text.count("“") != text.count("”"):
        return [("dialogue", text)]
    parts: list[tuple[str, str]] = []
    position = 0
    for match in _QUOTED.finditer(text):
        parts.append(("narration", text[position:match.start()]))
        parts.append(("dialogue", match.group(0)))
        position = match.end()
    parts.append(("narration", text[position:]))
    spoken = [part for part in parts if part[0] == "dialogue"]
    told = [(kind, piece.strip()) for kind, piece in parts if kind == "narration" and _WORD.search(piece)]
    if not spoken or not told:
        return [("dialogue", text)]
    return [(kind, piece.strip()) for kind, piece in parts
            if (kind == "dialogue" and piece.strip()) or (kind == "narration" and _WORD.search(piece))]


def check_page(reply: StoryPageReply, cast: Sequence[Mapping[str, Any]]) -> CheckedPage:
    """The page the reply describes, with each line's speaker decided against ``cast``."""
    cast_ids = {str(character["id"]): str(character["id"]) for character in cast}
    ids = dict(cast_ids)
    names: dict[str, str] = {}
    for character in cast:
        for name in (character.get("name"), *(character.get("aliases") or [])):
            if _key(name):
                names.setdefault(_key(name), str(character["id"]))

    proposed: dict[str, str] = {}
    new_characters: list[dict[str, Any]] = []
    room = max(0, min(NEW_CHARACTERS_MAX, CHARACTERS_MAX - len(cast)))
    for item in reply.new_characters:
        name = _clean_line(item.name, NAME_MAX)
        raw_id = item.id.strip()
        if not name:
            continue
        existing = cast_ids.get(raw_id) or names.get(_key(name))
        if existing:
            # The cast already has them: their lines are theirs.
            proposed[raw_id] = existing
            continue
        if len(new_characters) >= room:
            continue
        base = _slug(raw_id) or _slug(name) or f"character-{len(new_characters) + 1}"
        new_id, suffix = base, 2
        while new_id in ids:
            new_id, suffix = f"{base}-{suffix}", suffix + 1
        ids[new_id] = new_id
        names.setdefault(_key(name), new_id)
        if raw_id:
            proposed[raw_id] = new_id
        new_characters.append({"id": new_id, "name": name,
                               "description": _clean_line(item.description, DESCRIPTION_MAX)})

    def speaker(value: str | None) -> str | None:
        raw = (value or "").strip()
        if not raw:
            return None
        return proposed.get(raw) or ids.get(raw) or names.get(_key(raw))

    blocks: list[dict[str, Any]] = []
    for item in reply.blocks[:PAGE_BLOCKS_MAX]:
        text = _clean_text(item.text, BLOCK_TEXT_MAX)
        if not text:
            continue
        if item.kind == "narration":
            blocks.append({"kind": "narration", "text": text})
            continue
        speaker_id = speaker(item.speaker_id)
        # Unknown speakers are kept as the model named them, for the writer to see, and flagged.
        named = _slug(item.speaker_id)
        line = ({"speaker_id": speaker_id} if speaker_id
                else {**({"speaker_id": named} if named else {}), "attribution": UNVERIFIED})
        for kind, piece in _spoken_parts(text):
            blocks.append({"kind": "dialogue", **line, "text": piece} if kind == "dialogue"
                          else {"kind": "narration", "text": piece})

    moves: list[str] = []
    for move in reply.suggested_moves:
        text = _clean_line(move, MOVE_MAX)
        if text and text.casefold() not in {seen.casefold() for seen in moves}:
            moves.append(text)
    return CheckedPage(title=_clean_line(reply.title, TITLE_MAX) or None, blocks=blocks,
                       new_characters=new_characters, suggested_moves=moves[:SUGGESTED_MOVES_MAX],
                       summary=_clean_line(reply.summary, SUMMARY_MAX))


def tagged_text(blocks: Sequence[Mapping[str, Any]]) -> str:
    """A page as prompt material: a spoken line starts with its speaker's id in brackets."""
    lines = []
    for block in blocks:
        text = str(block.get("text") or "").strip()
        if not text:
            continue
        speaker_id = block.get("speaker_id")
        lines.append(f"[{speaker_id}] {text}" if block.get("kind") == "dialogue" and speaker_id else text)
    return "\n\n".join(lines)
