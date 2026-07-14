from __future__ import annotations

import pytest

from app.rpg.narrative_engine import (
    DeterministicBeatPlanner,
    DeterministicNarrativeWriter,
    PresentationProfile,
    StructuredNarrativeWriter,
    TurnPresentationRequest,
    bran_fixture_evidence,
    writer_payload,
)


def _request() -> TurnPresentationRequest:
    return TurnPresentationRequest(
        request_id="request:writer",
        turn_id="turn:writer",
        campaign_id="campaign:writer",
        player_input="How is the road?",
        actor_ids=("npc:bran",),
        target_actor_id="npc:bran",
        presentation_profile=PresentationProfile.FAST,
        metadata={"response_mode": "dialogue"},
    )


def test_writer_payload_contains_only_approved_evidence() -> None:
    request = _request()
    evidence = bran_fixture_evidence()
    plan = DeterministicBeatPlanner().plan(request, evidence)
    payload = writer_payload(request, plan, evidence)
    approved = {ref for beat in plan.beats for ref in beat.evidence_refs}
    assert {row["evidence_id"] for row in payload["approved_evidence"]}.issubset(approved)
    assert payload["player_input"] == request.player_input
    assert payload["beats"][0]["sequence"] == 1


def test_structured_writer_maps_exactly_one_block_per_beat() -> None:
    request = _request()
    evidence = bran_fixture_evidence()
    plan = DeterministicBeatPlanner().plan(request, evidence)

    def generate(payload):
        return {
            "blocks": [
                {
                    "beat_id": beat["beat_id"],
                    "sequence": beat["sequence"],
                    "kind": beat["kind"],
                    "purpose": beat["purpose"],
                    "speaker_id": beat.get("speaker_id"),
                    "text": f"Rendered {beat['purpose']}.",
                }
                for beat in payload["beats"]
            ]
        }

    result = StructuredNarrativeWriter(generate, provider="fixture").write(request, plan, evidence)
    assert len(result.blocks) == len(plan.beats)
    assert [block.sequence for block in result.blocks] == list(range(1, len(result.blocks) + 1))
    assert result.source == "structured_provider"


def test_structured_writer_rejects_extra_or_changed_beats() -> None:
    request = _request()
    evidence = bran_fixture_evidence()
    plan = DeterministicBeatPlanner().plan(request, evidence)

    def generate(_payload):
        return {
            "blocks": [
                {
                    "beat_id": plan.beats[0].beat_id,
                    "sequence": 99,
                    "kind": plan.beats[0].kind.value,
                    "purpose": plan.beats[0].purpose.value,
                    "speaker_id": plan.beats[0].speaker_id,
                    "text": "Changed order.",
                }
            ]
        }

    with pytest.raises(ValueError):
        StructuredNarrativeWriter(generate).write(request, plan, evidence)


def test_deterministic_writer_produces_canonical_blocks_without_legacy_payloads() -> None:
    request = _request()
    evidence = bran_fixture_evidence()
    plan = DeterministicBeatPlanner().plan(request, evidence)
    result = DeterministicNarrativeWriter().write(request, plan, evidence)
    assert len(result.blocks) == len(plan.beats)
    assert result.blocks[0].text.startswith("Bran pauses")
    assert result.blocks[1].speaker_id == "npc:bran"
    assert result.source == "deterministic_writer"
