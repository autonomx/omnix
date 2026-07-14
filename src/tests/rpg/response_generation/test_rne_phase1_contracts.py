from __future__ import annotations

from app.rpg.narrative_engine import (
    AuthorityClass,
    BeatKind,
    BeatPurpose,
    CanonicalNarrativeResponse,
    DeliveryMetadata,
    DeliveryMode,
    EvidenceRecord,
    GenerationMetadata,
    NarrativeBeat,
    NarrativeBlock,
    PresentationProfile,
    TurnPresentationRequest,
    ValidationReport,
    VisibilityClass,
    stable_hash,
)


def test_turn_presentation_request_hash_is_deterministic() -> None:
    request = TurnPresentationRequest(
        request_id="request:1",
        turn_id="turn:1",
        campaign_id="campaign:1",
        player_input="Ask Bran about the road.",
        actor_ids=("npc:bran",),
        target_actor_id="npc:bran",
        presentation_profile=PresentationProfile.IMMERSIVE,
    )
    assert request.request_hash == stable_hash(request.as_dict())
    assert request.request_hash.startswith("sha256:")


def test_authority_and_visibility_are_independent() -> None:
    belief = EvidenceRecord(
        evidence_id="npc:vexira:belief:unmaker",
        content="Vexira believes the player is the returned Unmaker.",
        authority=AuthorityClass.NPC_BELIEF,
        visibility=VisibilityClass.NPC_PRIVATE,
        known_by=("npc:vexira",),
    )
    payload = belief.as_dict()
    assert payload["authority"] == "npc_belief"
    assert payload["visibility"] == "npc_private"


def test_response_content_hash_excludes_delivery_progress() -> None:
    block = NarrativeBlock(
        block_id="block:1",
        beat_id="beat:1",
        sequence=1,
        kind=BeatKind.DIALOGUE,
        purpose=BeatPurpose.DIRECT_ANSWER,
        text="The road is muddy, but passable.",
        speaker_id="npc:bran",
    )
    base = CanonicalNarrativeResponse(
        response_id="response:1",
        request_id="request:1",
        turn_id="turn:1",
        campaign_id="campaign:1",
        revision=1,
        blocks=(block,),
        evidence_used=(),
        validation=ValidationReport(passed=True),
        generation=GenerationMetadata(source="deterministic", beat_count=1),
        delivery=DeliveryMetadata(mode=DeliveryMode.BLOCKING, status="complete"),
    ).with_content_hash()
    deferred = CanonicalNarrativeResponse(
        response_id=base.response_id,
        request_id=base.request_id,
        turn_id=base.turn_id,
        campaign_id=base.campaign_id,
        revision=base.revision,
        blocks=base.blocks,
        evidence_used=base.evidence_used,
        validation=base.validation,
        generation=base.generation,
        delivery=DeliveryMetadata(mode=DeliveryMode.DEFERRED, status="pending"),
    ).with_content_hash()
    assert base.content_hash == deferred.content_hash


def test_narrative_beat_requires_explicit_sequence_and_purpose() -> None:
    beat = NarrativeBeat(
        beat_id="beat:reaction",
        sequence=1,
        kind=BeatKind.NARRATION,
        purpose=BeatPurpose.PHYSICAL_REACTION,
        evidence_refs=("npc:bran:habit",),
    )
    assert beat.as_dict()["sequence"] == 1
    assert beat.as_dict()["purpose"] == "physical_reaction"
