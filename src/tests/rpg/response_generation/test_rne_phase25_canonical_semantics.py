from __future__ import annotations

from dataclasses import replace

from app.rpg.narrative_engine import (
    BeatKind,
    BeatPurpose,
    CanonicalNarrativeRenderer,
    CanonicalNarrativeResponse,
    DeliveryMetadata,
    DeliveryMode,
    GenerationMetadata,
    NarrativeBeat,
    NarrativeBlock,
    NarrativePlan,
    NarrativeValidator,
    PresentationProfile,
    TurnPresentationRequest,
    ValidationReport,
    canonical_consumer_bundle,
)


def _blocks() -> tuple[NarrativeBlock, ...]:
    return (
        NarrativeBlock(
            block_id="block:reaction",
            beat_id="beat:reaction",
            sequence=1,
            kind=BeatKind.NARRATION,
            purpose=BeatPurpose.PHYSICAL_REACTION,
            text="Bran lowers the iron latch and turns toward the rain-streaked window.",
        ),
        NarrativeBlock(
            block_id="block:movement",
            beat_id="beat:movement",
            sequence=2,
            kind=BeatKind.NARRATION,
            purpose=BeatPurpose.ENVIRONMENTAL_CHANGE,
            text="Bran lowers the iron latch, then turns toward the rain-streaked window.",
        ),
    )


def _response() -> CanonicalNarrativeResponse:
    return CanonicalNarrativeResponse(
        response_id="response:phase25",
        request_id="request:phase25",
        turn_id="turn:phase25",
        campaign_id="campaign:phase25",
        revision=1,
        blocks=_blocks(),
        evidence_used=("evidence:latch", "evidence:rain"),
        validation=ValidationReport(passed=True),
        generation=GenerationMetadata(
            source="structured_provider",
            provider="provider:a",
            model="model:a",
            latency_ms=12.5,
            attempt_count=1,
            evidence_count=2,
            beat_count=2,
        ),
        delivery=DeliveryMetadata(mode=DeliveryMode.BLOCKING, status="complete"),
    ).with_content_hash()


def test_semantic_hash_excludes_provider_latency_retry_and_delivery_metadata() -> None:
    response = _response()
    operational_variant = replace(
        response,
        generation=GenerationMetadata(
            source="structured_provider",
            provider="provider:b",
            model="model:b",
            latency_ms=938.2,
            attempt_count=4,
            evidence_count=2,
            beat_count=2,
            metadata={"trace_id": "different"},
        ),
        delivery=DeliveryMetadata(
            mode=DeliveryMode.DEFERRED,
            status="pending",
            metadata={"queue": "background"},
        ),
        content_hash="",
    ).with_content_hash()
    assert operational_variant.content_hash == response.content_hash
    assert operational_variant.semantic_content_payload() == response.semantic_content_payload()
    assert operational_variant.as_dict()["generation"] != response.as_dict()["generation"]
    assert operational_variant.as_dict()["delivery"] != response.as_dict()["delivery"]


def test_every_consumer_preserves_exact_approved_block_membership_and_order() -> None:
    response = _response()
    bundle = canonical_consumer_bundle(response)
    expected = ["block:reaction", "block:movement"]
    assert list(CanonicalNarrativeRenderer().render(response).block_ids) == expected
    assert [row["block_id"] for row in bundle["transcript"]] == expected
    assert [row["block_id"] for row in bundle["tts"]] == expected
    assert bundle["journal"]["block_ids"] == expected
    assert [row["block_id"] for row in bundle["report"]["blocks"]] == expected
    assert [row["block_id"] for row in bundle["replay"]["blocks"]] == expected


def test_likely_duplicate_events_fail_before_canonical_approval() -> None:
    request = TurnPresentationRequest(
        request_id="request:phase25",
        turn_id="turn:phase25",
        campaign_id="campaign:phase25",
        player_input="Watch Bran close the window.",
    )
    plan = NarrativePlan(
        request_id=request.request_id,
        mode="observation",
        profile=PresentationProfile.IMMERSIVE,
        word_budget=(1, 100),
        beats=(
            NarrativeBeat(
                beat_id="beat:reaction",
                sequence=1,
                kind=BeatKind.NARRATION,
                purpose=BeatPurpose.PHYSICAL_REACTION,
            ),
            NarrativeBeat(
                beat_id="beat:movement",
                sequence=2,
                kind=BeatKind.NARRATION,
                purpose=BeatPurpose.ENVIRONMENTAL_CHANGE,
            ),
        ),
        must_answer="Show the physical response.",
        metadata={},
    )
    report = NarrativeValidator().validate(request, plan, (), _blocks())
    assert report.passed is False
    assert any(issue.code == "duplicate_event" for issue in report.issues)
