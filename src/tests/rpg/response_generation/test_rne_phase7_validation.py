from __future__ import annotations

from app.rpg.narrative_engine import (
    DeterministicBeatPlanner,
    NarrativeBlock,
    NarrativeValidator,
    PresentationProfile,
    TurnPresentationRequest,
    WriterResult,
    bran_fixture_evidence,
    write_validate_repair,
)


def _setup():
    request = TurnPresentationRequest(
        request_id="request:validation",
        turn_id="turn:validation",
        campaign_id="campaign:validation",
        player_input="How is the road?",
        actor_ids=("npc:bran",),
        target_actor_id="npc:bran",
        presentation_profile=PresentationProfile.FAST,
        metadata={"response_mode": "dialogue"},
    )
    evidence = bran_fixture_evidence()
    plan = DeterministicBeatPlanner().plan(request, evidence)
    return request, evidence, plan


def _block_from_beat(beat, text: str) -> NarrativeBlock:
    return NarrativeBlock(
        block_id=f"block:{beat.beat_id}",
        beat_id=beat.beat_id,
        sequence=beat.sequence,
        kind=beat.kind,
        purpose=beat.purpose,
        text=text,
        speaker_id=beat.speaker_id,
        evidence_refs=beat.evidence_refs,
        claim_refs=beat.required_claim_refs,
    )


def test_validator_rejects_mixed_script_corruption() -> None:
    request, evidence, plan = _setup()
    blocks = tuple(
        _block_from_beat(beat, "Bran answers with broken text مرحبا." if index == 1 else "Bran pauses.")
        for index, beat in enumerate(plan.beats)
    )
    report = NarrativeValidator().validate(request, plan, evidence, blocks)
    assert report.passed is False
    assert "mixed_script_corruption" in {issue.code for issue in report.issues}


def test_validator_rejects_unplanned_evidence_and_speaker() -> None:
    request, evidence, plan = _setup()
    first, second = plan.beats[:2]
    blocks = (
        _block_from_beat(first, "Bran pauses."),
        NarrativeBlock(
            block_id="block:bad",
            beat_id=second.beat_id,
            sequence=second.sequence,
            kind=second.kind,
            purpose=second.purpose,
            text="The road is open.",
            speaker_id="npc:vexira",
            evidence_refs=("npc:vexira:gm_secret",),
        ),
    )
    report = NarrativeValidator().validate(request, plan, evidence, blocks)
    codes = {issue.code for issue in report.issues}
    assert "speaker_changed" in codes
    assert "invalid_speaker" in codes
    assert "unknown_evidence" in codes


def test_mechanical_label_repair_can_be_revalidated() -> None:
    request, evidence, plan = _setup()

    class LabelWriter:
        def write(self, _request, _plan, _evidence):
            blocks = tuple(
                _block_from_beat(beat, f"NPC: grounded {beat.purpose.value} response.")
                for beat in plan.beats
            )
            return WriterResult(blocks=blocks, source="fixture")

    result = write_validate_repair(request, plan, evidence, LabelWriter())
    assert result.validation.passed is True
    assert result.fallback_used is False
    assert result.validation.repair_history
    assert all(not block.text.startswith("NPC:") for block in result.writer_result.blocks)


def test_invalid_provider_output_falls_back_to_deterministic_blocks() -> None:
    request, evidence, plan = _setup()

    class BrokenWriter:
        def write(self, _request, _plan, _evidence):
            raise ValueError("provider output was malformed")

    result = write_validate_repair(request, plan, evidence, BrokenWriter())
    assert result.fallback_used is True
    assert result.validation.passed is True
    assert result.writer_result.source == "deterministic_writer"
    assert len(result.writer_result.blocks) == len(plan.beats)
