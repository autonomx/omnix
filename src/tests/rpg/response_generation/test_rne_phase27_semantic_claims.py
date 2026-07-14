from __future__ import annotations

from app.rpg.narrative_engine import (
    AuthorityClass,
    BeatKind,
    BeatPurpose,
    CanonicalNarrativeResponse,
    ClaimAssertion,
    DeliveryMetadata,
    DeliveryMode,
    EvidenceRecord,
    GenerationMetadata,
    NarrativeBeat,
    NarrativeBlock,
    NarrativePlan,
    NarrativeValidator,
    PresentationProfile,
    TurnPresentationRequest,
    ValidationReport,
    VisibilityClass,
    canonical_response_from_dict,
)
from app.rpg.narrative_engine.validation import write_validate_repair
from app.rpg.narrative_engine.writer import WriterResult


class _Writer:
    def __init__(self, block: NarrativeBlock) -> None:
        self.block = block

    def write(self, request, plan, evidence) -> WriterResult:
        return WriterResult(
            blocks=(self.block,),
            source="structured_provider",
            provider="fixture",
            model="claim-test",
        )


def _request(
    *,
    claim_id: str | None = None,
    ledger: dict | None = None,
) -> TurnPresentationRequest:
    refs = (claim_id,) if claim_id else ()
    return TurnPresentationRequest(
        request_id="request:phase27",
        turn_id="turn:phase27",
        campaign_id="campaign:phase27",
        player_input="What is true here?",
        actor_ids=("npc:bran",),
        target_actor_id="npc:bran",
        authoritative_outcome={
            "allowed_claim_refs": list(refs),
            "claim_ledger": ledger or {},
        },
        metadata={"response_mode": "dialogue"},
    )


def _plan(claim_id: str | None = None) -> NarrativePlan:
    refs = (claim_id,) if claim_id else ()
    return NarrativePlan(
        request_id="request:phase27",
        mode="dialogue",
        profile=PresentationProfile.IMMERSIVE,
        word_budget=(1, 80),
        beats=(
            NarrativeBeat(
                beat_id="beat:answer",
                sequence=1,
                kind=BeatKind.DIALOGUE,
                purpose=BeatPurpose.DIRECT_ANSWER,
                speaker_id="npc:bran",
                evidence_refs=("evidence:road",),
                required_claim_refs=refs,
                metadata={"evidence_scope": "speaker"},
            ),
        ),
        must_answer="Answer directly.",
        metadata={},
    )


def _evidence(authority: AuthorityClass = AuthorityClass.OBJECTIVE_CANON) -> tuple[EvidenceRecord, ...]:
    return (
        EvidenceRecord(
            evidence_id="evidence:road",
            content="The east road is muddy but passable.",
            authority=authority,
            visibility=VisibilityClass.PUBLIC,
            entity_refs=("location:east_road", "npc:bran"),
        ),
    )


def _block(
    text: str,
    *,
    claim: ClaimAssertion | None = None,
    claim_ref: str | None = None,
) -> NarrativeBlock:
    return NarrativeBlock(
        block_id="block:answer",
        beat_id="beat:answer",
        sequence=1,
        kind=BeatKind.DIALOGUE,
        purpose=BeatPurpose.DIRECT_ANSWER,
        text=text,
        speaker_id="npc:bran",
        evidence_refs=("evidence:road",),
        claim_refs=(claim_ref,) if claim_ref else (),
        claims=(claim,) if claim else (),
        metadata={
            "writer_contract": "structured_v3",
            "claim_source": "provider" if claim else "pending_inference",
            "evidence_scope": "speaker",
        },
    )


def _validate(
    block: NarrativeBlock,
    *,
    request: TurnPresentationRequest | None = None,
    plan: NarrativePlan | None = None,
    evidence: tuple[EvidenceRecord, ...] | None = None,
):
    return NarrativeValidator().validate(
        request or _request(),
        plan or _plan(),
        evidence or _evidence(),
        (block,),
    )


def test_supported_explicit_claim_passes_semantic_grounding() -> None:
    claim = ClaimAssertion(
        claim_id="claim:road",
        text="The east road is muddy but passable.",
        authority=AuthorityClass.OBJECTIVE_CANON,
        evidence_refs=("evidence:road",),
        scope="speaker",
    )
    result = write_validate_repair(
        _request(),
        _plan(),
        _evidence(),
        _Writer(_block(claim.text, claim=claim)),
    )
    assert result.validation.passed is True, result.validation.as_dict()
    assert result.validation.metadata["semantic_grounding_passed"] is True
    assert result.validation.metadata["explicit_claim_count"] == 1


def test_unsupported_factual_claim_is_rejected_before_fallback() -> None:
    claim = ClaimAssertion(
        claim_id="claim:bridge",
        text="The stone bridge has collapsed into the river.",
        authority=AuthorityClass.OBJECTIVE_CANON,
        evidence_refs=("evidence:road",),
        scope="speaker",
    )
    report = _validate(_block(claim.text, claim=claim))
    assert report.passed is False
    assert any(
        issue.code == "unsupported_claim_text"
        for issue in report.issues
    )


def test_npc_belief_cannot_validate_as_objective_canon() -> None:
    claim = ClaimAssertion(
        claim_id="claim:belief",
        text="The east road is muddy but passable.",
        authority=AuthorityClass.OBJECTIVE_CANON,
        evidence_refs=("evidence:road",),
        scope="speaker",
    )
    report = _validate(
        _block(claim.text, claim=claim),
        evidence=_evidence(AuthorityClass.NPC_BELIEF),
    )
    assert report.passed is False
    assert any(
        issue.code == "claim_authority_unsupported"
        for issue in report.issues
    )


def test_authoritative_state_claim_must_match_ledger_value() -> None:
    claim_id = "currency.gold"
    ledger = {
        claim_id: {
            "text": "The player now has twelve gold.",
            "authority": "confirmed_turn",
            "scope": "speaker",
            "subject_id": "player",
            "predicate": "gold_balance",
            "value": 12,
        }
    }
    claim = ClaimAssertion(
        claim_id=claim_id,
        text="The east road is muddy but passable.",
        authority=AuthorityClass.CONFIRMED_TURN,
        evidence_refs=("evidence:road",),
        scope="speaker",
        subject_id="player",
        predicate="gold_balance",
        value=99,
    )
    request = _request(claim_id=claim_id, ledger=ledger)
    plan = _plan(claim_id)
    report = _validate(
        _block(claim.text, claim=claim, claim_ref=claim_id),
        request=request,
        plan=plan,
        evidence=_evidence(AuthorityClass.CONFIRMED_TURN),
    )
    assert report.passed is False
    assert any(
        issue.code == "authoritative_claim_mismatch"
        for issue in report.issues
    )


def test_inferred_claims_are_attached_to_compatibility_output() -> None:
    result = write_validate_repair(
        _request(),
        _plan(),
        _evidence(),
        _Writer(_block("The east road is muddy but passable.")),
    )
    assert result.validation.passed is True, result.validation.as_dict()
    assert len(result.writer_result.blocks[0].claims) == 1
    assert result.writer_result.blocks[0].metadata["claim_source"] == "inferred"


def test_claim_ledger_survives_serialization_and_semantic_hash_roundtrip() -> None:
    claim = ClaimAssertion(
        claim_id="claim:road",
        text="The east road is muddy but passable.",
        authority=AuthorityClass.OBJECTIVE_CANON,
        evidence_refs=("evidence:road",),
        scope="speaker",
        subject_id="location:east_road",
        predicate="condition",
        value="muddy_but_passable",
    )
    response = CanonicalNarrativeResponse(
        response_id="response:phase27",
        request_id="request:phase27",
        turn_id="turn:phase27",
        campaign_id="campaign:phase27",
        revision=1,
        blocks=(_block(claim.text, claim=claim),),
        evidence_used=("evidence:road",),
        validation=ValidationReport(passed=True),
        generation=GenerationMetadata(source="fixture"),
        delivery=DeliveryMetadata(mode=DeliveryMode.BLOCKING),
    ).with_content_hash()
    restored = canonical_response_from_dict(response.as_dict())
    assert restored.content_hash == response.content_hash
    assert restored.blocks[0].claims == (claim,)
