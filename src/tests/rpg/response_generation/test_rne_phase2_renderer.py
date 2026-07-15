from __future__ import annotations

from app.rpg.narrative_engine import (
    BeatKind,
    BeatPurpose,
    CanonicalNarrativeRenderer,
    CanonicalNarrativeResponse,
    DeliveryMetadata,
    DeliveryMode,
    GenerationMetadata,
    NarrativeBlock,
    ValidationReport,
    legacy_response_projection,
    transcript_projection,
    tts_projection,
)


def _response(*blocks: NarrativeBlock) -> CanonicalNarrativeResponse:
    return CanonicalNarrativeResponse(
        response_id="response:test",
        request_id="request:test",
        turn_id="turn:test",
        campaign_id="campaign:test",
        revision=1,
        blocks=tuple(blocks),
        evidence_used=(),
        validation=ValidationReport(passed=True),
        generation=GenerationMetadata(source="fixture", beat_count=len(blocks)),
        delivery=DeliveryMetadata(mode=DeliveryMode.BLOCKING),
    ).with_content_hash()


def _block(
    block_id: str,
    sequence: int,
    kind: BeatKind,
    purpose: BeatPurpose,
    text: str,
    speaker_id: str | None = None,
) -> NarrativeBlock:
    return NarrativeBlock(
        block_id=block_id,
        beat_id=f"beat:{block_id}",
        sequence=sequence,
        kind=kind,
        purpose=purpose,
        text=text,
        speaker_id=speaker_id,
    )


def test_renderer_preserves_vexira_style_alternating_sequence() -> None:
    response = _response(
        _block("ultimatum", 6, BeatKind.DIALOGUE, BeatPurpose.ULTIMATUM, "Choose.", "npc:vexira"),
        _block("reaction", 1, BeatKind.NARRATION, BeatPurpose.PHYSICAL_REACTION, "Vexira stops circling."),
        _block("rebuttal", 2, BeatKind.DIALOGUE, BeatPurpose.DIRECT_ANSWER, "You were pulled through.", "npc:vexira"),
        _block("movement", 3, BeatKind.NARRATION, BeatPurpose.MOVEMENT, "Violet smoke follows her hand."),
        _block("lore", 4, BeatKind.DIALOGUE, BeatPurpose.LORE_REVEAL, "The Academy mistakes ceremony for destiny.", "npc:vexira"),
        _block("ritual", 5, BeatKind.NARRATION, BeatPurpose.EMOTIONAL_ESCALATION, "Her dagger scores the mirrorstone."),
    )
    rendered = CanonicalNarrativeRenderer().render(response)
    assert rendered.block_ids == ("reaction", "rebuttal", "movement", "lore", "ritual", "ultimatum")
    assert rendered.text.index("stops circling") < rendered.text.index("pulled through")
    assert rendered.text.index("pulled through") < rendered.text.index("Violet smoke")
    assert rendered.text.index("mirrorstone") < rendered.text.index("Choose")


def test_duplicate_bran_line_is_rendered_once() -> None:
    response = _response(
        _block("narration-copy", 1, BeatKind.NARRATION, BeatPurpose.DIRECT_ANSWER, "Bran says the road is muddy but passable."),
        _block("dialogue", 2, BeatKind.DIALOGUE, BeatPurpose.DIRECT_ANSWER, "Bran says the road is muddy but passable.", "npc:bran"),
    )
    rendered = CanonicalNarrativeRenderer().render(response)
    assert rendered.text.count("muddy but passable") == 1
    assert len(rendered.blocks) == 1


def test_legacy_fields_are_projections_of_canonical_blocks() -> None:
    response = _response(
        _block("reaction", 1, BeatKind.NARRATION, BeatPurpose.PHYSICAL_REACTION, "Bran pauses over the cup."),
        _block("answer", 2, BeatKind.DIALOGUE, BeatPurpose.DIRECT_ANSWER, "Busy enough to keep the hearth warm.", "npc:bran"),
    )
    projected = legacy_response_projection(response)
    assert projected["narration"] == "Bran pauses over the cup."
    assert projected["npc"] == {"speaker": "npc:bran", "line": "Busy enough to keep the hearth warm."}
    assert projected["visible_response"]["response_id"] == response.response_id
    assert [row["block_id"] for row in transcript_projection(response)] == ["reaction", "answer"]
    assert [row["speaker_id"] for row in tts_projection(response)] == ["narrator", "npc:bran"]
