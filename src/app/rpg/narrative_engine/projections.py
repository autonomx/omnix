"""Boundary projections derived from canonical narrative blocks."""
from __future__ import annotations

from typing import Any, Iterable

from .authority import BeatKind
from .contracts import CanonicalNarrativeResponse, NarrativeBlock
from .renderer import CanonicalNarrativeRenderer, deduplicate_blocks, render_block_text


def _blocks(response: CanonicalNarrativeResponse) -> tuple[NarrativeBlock, ...]:
    return deduplicate_blocks(response.blocks)


def legacy_response_projection(response: CanonicalNarrativeResponse) -> dict[str, Any]:
    """Project canonical blocks into temporary legacy API fields.

    The projection is calculated at the boundary and is never authoritative.
    """

    blocks = _blocks(response)
    narration_blocks = tuple(
        block
        for block in blocks
        if block.kind in {BeatKind.NARRATION, BeatKind.ACTION, BeatKind.RESULT, BeatKind.STATE_CHANGE}
    )
    dialogue_blocks = tuple(block for block in blocks if block.kind is BeatKind.DIALOGUE)
    narration = "\n\n".join(render_block_text(block) for block in narration_blocks).strip()
    dialogue_payload = [
        {
            "block_id": block.block_id,
            "speaker_id": block.speaker_id or "",
            "text": block.text.strip(),
            "sequence": block.sequence,
        }
        for block in dialogue_blocks
    ]
    npc = {}
    if len(dialogue_payload) == 1:
        npc = {
            "speaker": dialogue_payload[0]["speaker_id"],
            "line": dialogue_payload[0]["text"],
        }
    plain_text = CanonicalNarrativeRenderer().render(response).text
    return {
        "narration": narration,
        "final_narration": narration,
        "summary": plain_text,
        "npc": npc,
        "dialogue_blocks": dialogue_payload,
        "visible_response": {
            "format_version": "rpg_visible_response_v2",
            "response_id": response.response_id,
            "narration": narration,
            "messages": [
                {
                    "kind": "npc",
                    "speaker_id": item["speaker_id"],
                    "text": item["text"],
                    "block_id": item["block_id"],
                    "sequence": item["sequence"],
                }
                for item in dialogue_payload
            ],
            "plain_text": plain_text,
        },
    }


def transcript_projection(response: CanonicalNarrativeResponse) -> list[dict[str, Any]]:
    return [
        {
            "response_id": response.response_id,
            "block_id": block.block_id,
            "sequence": block.sequence,
            "kind": block.kind.value,
            "speaker_id": block.speaker_id,
            "text": block.text.strip(),
        }
        for block in _blocks(response)
    ]


def tts_projection(response: CanonicalNarrativeResponse) -> list[dict[str, str]]:
    return [
        {
            "block_id": block.block_id,
            "speaker_id": block.speaker_id or "narrator",
            "text": block.text.strip(),
        }
        for block in _blocks(response)
        if block.text.strip()
    ]


def journal_projection(response: CanonicalNarrativeResponse) -> dict[str, Any]:
    rendered = CanonicalNarrativeRenderer().render(response)
    return {
        "response_id": response.response_id,
        "turn_id": response.turn_id,
        "campaign_id": response.campaign_id,
        "text": rendered.text,
        "block_ids": list(rendered.block_ids),
        "evidence_used": list(response.evidence_used),
    }


def projection_block_ids(rows: Iterable[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(str(row.get("block_id") or "") for row in rows if row.get("block_id"))
