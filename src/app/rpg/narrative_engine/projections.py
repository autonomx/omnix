"""Boundary projections derived from canonical narrative blocks."""
from __future__ import annotations

from typing import Any, Iterable

from .authority import BeatKind, BeatPurpose
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
            "content_hash": response.content_hash or response.with_content_hash().content_hash,
            "narration": narration,
            "messages": [
                {
                    "kind": "npc",
                    "speaker": item["speaker_id"],
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
            "content_hash": response.content_hash or response.with_content_hash().content_hash,
            "block_id": block.block_id,
            "sequence": block.sequence,
            "kind": block.kind.value,
            "purpose": block.purpose.value,
            "speaker_id": block.speaker_id,
            "text": block.text.strip(),
        }
        for block in _blocks(response)
    ]


def tts_projection(response: CanonicalNarrativeResponse) -> list[dict[str, str]]:
    return [
        {
            "response_id": response.response_id,
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
        "content_hash": response.content_hash or response.with_content_hash().content_hash,
        "turn_id": response.turn_id,
        "campaign_id": response.campaign_id,
        "text": rendered.text,
        "block_ids": list(rendered.block_ids),
        "evidence_used": list(response.evidence_used),
    }


def recap_projection(response: CanonicalNarrativeResponse) -> dict[str, Any]:
    blocks = _blocks(response)
    consequential = [
        block
        for block in blocks
        if block.purpose
        in {
            BeatPurpose.CONSEQUENCE,
            BeatPurpose.RESOLVED_ACTION,
            BeatPurpose.LORE_REVEAL,
            BeatPurpose.ENVIRONMENTAL_CHANGE,
        }
    ]
    selected = consequential or list(blocks)
    return {
        "response_id": response.response_id,
        "content_hash": response.content_hash or response.with_content_hash().content_hash,
        "turn_id": response.turn_id,
        "text": " ".join(block.text.strip() for block in selected if block.text.strip()),
        "block_ids": [block.block_id for block in selected],
    }


def report_projection(response: CanonicalNarrativeResponse) -> dict[str, Any]:
    return {
        "response_id": response.response_id,
        "request_id": response.request_id,
        "turn_id": response.turn_id,
        "campaign_id": response.campaign_id,
        "revision": response.revision,
        "content_hash": response.content_hash or response.with_content_hash().content_hash,
        "validation": response.validation.as_dict(),
        "generation": {
            "source": response.generation.source,
            "provider": response.generation.provider,
            "model": response.generation.model,
            "latency_ms": response.generation.latency_ms,
            "evidence_count": response.generation.evidence_count,
            "beat_count": response.generation.beat_count,
            "hermes_used": response.generation.hermes_used,
        },
        "blocks": [block.as_dict() for block in _blocks(response)],
    }


def replay_projection(response: CanonicalNarrativeResponse) -> dict[str, Any]:
    frozen = response.with_content_hash()
    payload = frozen.as_dict()
    payload["projection_version"] = "rpg_narrative_replay_v1"
    payload["blocks"] = [block.as_dict() for block in _blocks(frozen)]
    return payload


def canonical_consumer_bundle(response: CanonicalNarrativeResponse) -> dict[str, Any]:
    """One immutable source bundle for UI, speech, logs, journals, reports, and replay."""
    frozen = response.with_content_hash()
    legacy = legacy_response_projection(frozen)
    return {
        "schema_version": "rpg_narrative_consumer_bundle_v1",
        "response_id": frozen.response_id,
        "content_hash": frozen.content_hash,
        "visible_response": legacy["visible_response"],
        "transcript": transcript_projection(frozen),
        "tts": tts_projection(frozen),
        "journal": journal_projection(frozen),
        "recap": recap_projection(frozen),
        "report": report_projection(frozen),
        "replay": replay_projection(frozen),
    }


def projection_block_ids(rows: Iterable[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(str(row.get("block_id") or "") for row in rows if row.get("block_id"))
