from __future__ import annotations

import pytest

from app.apps.rpg.narration.narrative_engine import (
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


def test_deterministic_writer_fits_long_evidence_into_the_word_budget() -> None:
    """A long lore page or dossier is cut at sentence ends: the fallback never overruns its budget."""
    from dataclasses import replace

    from app.apps.rpg.narration.narrative_engine.validation import NarrativeValidator

    request = _request()
    long_page = " ".join(f"Sentence {index} tells the road's long history in some detail." for index in range(80))
    evidence = tuple(replace(record, content=long_page) for record in bran_fixture_evidence())
    plan = DeterministicBeatPlanner().plan(request, evidence)
    result = DeterministicNarrativeWriter().write(request, plan, evidence)

    assert sum(len(block.text.split()) for block in result.blocks) <= plan.word_budget[1]
    assert all(block.text for block in result.blocks)
    report = NarrativeValidator().validate(request, plan, evidence, result.blocks)
    assert "word_budget_exceeded" not in {issue.code for issue in report.issues}


def test_deterministic_writer_never_has_a_character_recite_their_dossier() -> None:
    from app.apps.rpg.narration.narrative_engine import AuthorityClass, EvidenceRecord, VisibilityClass

    request = _request()
    evidence = (
        EvidenceRecord(
            evidence_id="runtime:npc:bran:profile",
            content="Bran. Keeps the Flagon since the war. Gruff but fair. Speaks in short sentences.",
            authority=AuthorityClass.OBJECTIVE_CANON,
            visibility=VisibilityClass.NARRATOR_ONLY,
            known_by=("npc:bran",),
            entity_refs=("npc:bran",),
        ),
        EvidenceRecord(
            evidence_id="canon:character:bran",
            content="Name: Bran\nRole: innkeeper of the Rusty Flagon",
            authority=AuthorityClass.OBJECTIVE_CANON,
            visibility=VisibilityClass.PUBLIC,
            entity_refs=("npc:bran",),
        ),
    )
    plan = DeterministicBeatPlanner().plan(request, evidence)
    result = DeterministicNarrativeWriter().write(request, plan, evidence)

    spoken = [block.text for block in result.blocks if block.speaker_id]
    assert spoken
    assert not any("Keeps the Flagon" in text or "Name:" in text for text in spoken)
