"""Ordered rendering for approved canonical narrative blocks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .authority import BeatKind
from .contracts import CanonicalNarrativeResponse, NarrativeBlock, ordered_blocks


@dataclass(frozen=True)
class RenderedNarrative:
    response_id: str
    text: str
    blocks: tuple[NarrativeBlock, ...]
    block_ids: tuple[str, ...]


def render_block_text(block: NarrativeBlock) -> str:
    text = block.text.strip()
    if not text:
        return ""
    if block.kind is BeatKind.DIALOGUE and not text.startswith(("\"", "“")):
        return f"“{text}”"
    return text


def render_plain_text(blocks: Iterable[NarrativeBlock]) -> str:
    rendered = [render_block_text(block) for block in ordered_blocks(tuple(blocks))]
    return "\n\n".join(text for text in rendered if text).strip()


class CanonicalNarrativeRenderer:
    """Render canonical blocks without changing planner sequence or membership."""

    def render(self, response: CanonicalNarrativeResponse) -> RenderedNarrative:
        blocks = ordered_blocks(response.blocks)
        return RenderedNarrative(
            response_id=response.response_id,
            text=render_plain_text(blocks),
            blocks=blocks,
            block_ids=tuple(block.block_id for block in blocks),
        )
