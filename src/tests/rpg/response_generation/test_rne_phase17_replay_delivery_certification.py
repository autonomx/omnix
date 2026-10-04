from __future__ import annotations

from app.rpg.narrative_engine import (
    BeatKind,
    BeatPurpose,
    CanonicalNarrativeResponse,
    DeliveryMetadata,
    DeliveryMode,
    GenerationMetadata,
    NarrativeBlock,
    ValidationReport,
)
from app.rpg.narrative_engine.certification import (
    certify_delivery_equivalence,
    certify_narrative_persistence_and_delivery,
    certify_narrative_roundtrip,
)


def _response() -> CanonicalNarrativeResponse:
    return CanonicalNarrativeResponse(
        response_id="response:phase17",
        request_id="request:phase17",
        turn_id="turn:phase17",
        campaign_id="campaign:phase17",
        revision=3,
        blocks=(
            NarrativeBlock(
                block_id="block:one",
                beat_id="beat:one",
                sequence=1,
                kind=BeatKind.NARRATION,
                purpose=BeatPurpose.PHYSICAL_REACTION,
                text="Bran glances toward the rain-dark road.",
                evidence_refs=("evidence:rain",),
            ),
            NarrativeBlock(
                block_id="block:two",
                beat_id="beat:two",
                sequence=2,
                kind=BeatKind.DIALOGUE,
                purpose=BeatPurpose.DIRECT_ANSWER,
                text="The bridge still holds.",
                speaker_id="npc:bran",
                evidence_refs=("evidence:bridge",),
            ),
        ),
        evidence_used=("evidence:rain", "evidence:bridge"),
        validation=ValidationReport(passed=True),
        generation=GenerationMetadata(
            source="fixture",
            provider="provider-free",
            model="deterministic",
            evidence_count=2,
            beat_count=2,
        ),
        delivery=DeliveryMetadata(mode=DeliveryMode.BLOCKING),
        metadata={"certification_fixture": True},
    ).with_content_hash()


def test_save_load_and_replay_recompute_identical_canonical_hash() -> None:
    report = certify_narrative_roundtrip(_response())
    assert report.passed is True
    assert all(report.checks.values())
    assert report.diagnostics["replayed_hash"] == report.content_hash
    assert report.diagnostics["block_ids"] == ["block:one", "block:two"]


def test_blocking_and_deferred_delivery_share_identical_content() -> None:
    report = certify_delivery_equivalence(_response())
    assert report.passed is True
    assert all(report.checks.values())
    assert report.diagnostics["delivered_block_ids"] == ["block:one", "block:two"]


def test_combined_certification_is_provider_free_and_complete() -> None:
    report = certify_narrative_persistence_and_delivery(_response())
    assert report["passed"] is True
    assert report["roundtrip"]["passed"] is True
    assert report["delivery"]["passed"] is True
