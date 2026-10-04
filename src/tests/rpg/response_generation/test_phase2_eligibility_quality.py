from __future__ import annotations

from dataclasses import replace

from app.rpg.response_generation.candidate_ranker import CandidateRanker
from app.rpg.response_generation.contracts import (
    AgencyEffect,
    CandidateSource,
    ResponseCandidate,
    ResponseMode,
    ResponseRequest,
    SectionType,
    SemanticResponsePlan,
    SemanticSection,
)
from app.rpg.response_generation.eligibility import EligibilityPolicy
from app.rpg.response_generation.orchestration import RpgResponseGenerator
from app.rpg.response_generation.quality_gate import QualityGate


def _candidate(
    candidate_id: str,
    text: str,
    *,
    claim_refs: tuple[str, ...] = ("fact.allowed",),
    speaker_id: str = "",
    section_type: SectionType = SectionType.RESULT,
    proposal_refs: tuple[str, ...] = (),
    metadata: dict | None = None,
    source: CandidateSource = CandidateSource.PROVIDER,
    relevance: float = 0.5,
    forward: float = 0.5,
    specificity: float = 0.5,
    naturalness: float = 0.5,
    provider_metadata: dict | None = None,
) -> ResponseCandidate:
    plan = SemanticResponsePlan(
        mode=ResponseMode.ACTION,
        sections=(
            SemanticSection(
                section_id=f"{candidate_id}.section",
                section_type=section_type,
                text=text,
                speaker_id=speaker_id,
                claim_refs=claim_refs,
                proposal_refs=proposal_refs,
            ),
        ),
        agency_effect=AgencyEffect.OFFER_ONLY,
        proposal_refs=proposal_refs,
        metadata=dict(metadata or {}),
    )
    return ResponseCandidate(
        candidate_id=candidate_id,
        plan=plan,
        source=source,
        current_turn_relevance=relevance,
        forward_motion=forward,
        specificity=specificity,
        naturalness=naturalness,
        provider_metadata=dict(provider_metadata or {}),
    )


def _request(**result_overrides) -> ResponseRequest:
    result = {
        "allowed_claim_refs": ["fact.allowed"],
        "strict_claim_refs": True,
        **result_overrides,
    }
    return ResponseRequest(
        turn_id="turn-2",
        player_input="Do it.",
        authoritative_turn_result=result,
        feature_flags={"strict_claim_refs": True},
    )


def test_phase2_ungrounded_beautiful_candidate_always_loses():
    beautiful = _candidate(
        "beautiful-unsupported",
        "The king crowns you before the cheering court.",
        claim_refs=("quest.crowned",),
        relevance=1.0,
        forward=1.0,
        specificity=1.0,
        naturalness=1.0,
    )
    awkward = _candidate(
        "awkward-grounded",
        "The attempt does not change your standing.",
        relevance=0.2,
        forward=0.2,
        specificity=0.2,
        naturalness=0.1,
        source=CandidateSource.DETERMINISTIC,
    )

    rendered = RpgResponseGenerator(
        candidate_adapter=lambda _request: (beautiful, awkward),
    ).generate(_request())

    assert rendered.metadata["candidate_id"] == "awkward-grounded"
    assert "crowns you" not in rendered.text
    assert rendered.metadata["eligible_candidate_count"] == 1


def test_phase2_visibility_speaker_proposal_and_agency_are_hard_gates():
    policy = EligibilityPolicy()
    request = _request(
        hidden_fact_refs=["fact.hidden"],
        allowed_speakers=["npc_bran"],
        speaker_knowledge_refs={"npc_bran": ["fact.allowed"]},
        approved_proposal_refs=["proposal.allowed"],
    )
    hidden = _candidate("hidden", "A hidden fact.", claim_refs=("fact.hidden",))
    speaker = _candidate(
        "speaker",
        "I know the answer.",
        speaker_id="npc_elara",
        section_type=SectionType.NPC_DIALOGUE,
    )
    proposal = _candidate(
        "proposal",
        "A new road is available.",
        proposal_refs=("proposal.unapproved",),
    )
    agency = _candidate(
        "agency",
        "You accept the investigation.",
        metadata={"auto_starts_investigation": True},
    )

    evaluated = [policy.evaluate(candidate, request) for candidate in (hidden, speaker, proposal, agency)]

    assert all(candidate.eligible is False for candidate in evaluated)
    assert any("hidden_reference" in reason for reason in evaluated[0].gate_decisions[1].reasons)
    assert any("invalid_speaker" in reason for reason in evaluated[1].gate_decisions[2].reasons)
    assert any("unapproved_proposal" in reason for reason in evaluated[2].gate_decisions[3].reasons)
    assert "player_choice_taken_without_authority" in evaluated[3].gate_decisions[4].reasons


def test_phase2_grounded_safe_fallback_outranks_stale_prior_narration():
    stale = _candidate(
        "stale",
        "You remember yesterday's tavern argument.",
        relevance=0.1,
        forward=0.0,
        naturalness=0.9,
        provider_metadata={"stale_prior_narration": True},
    )
    safe = _candidate(
        "safe",
        "Bran cannot confirm the name, but suggests asking Elara.",
        relevance=0.8,
        forward=0.8,
        naturalness=0.4,
        provider_metadata={"grounded_safe_fallback": True},
        source=CandidateSource.DETERMINISTIC,
    )
    policy = EligibilityPolicy()
    evaluated = tuple(policy.evaluate(candidate, _request()) for candidate in (stale, safe))

    assert CandidateRanker().select(evaluated).candidate_id == "safe"


def test_phase2_quality_gate_repairs_visible_duplicate_and_debug_prefix():
    candidate = _candidate(
        "repair",
        "Result: You open the door. You open the door.",
    )

    rendered = RpgResponseGenerator(
        candidate_adapter=lambda _request: (candidate,),
    ).generate(_request())

    assert rendered.text == "You open the door."
    assert rendered.quality_report["ok"] is True
    assert any("removed_debug_prefix" in item for item in rendered.repair_history)
    assert any("removed_duplicate_sentence" in item for item in rendered.repair_history)
    assert "Result:" not in rendered.text


def test_phase2_rewrite_is_called_once_and_rejected_when_it_adds_a_claim():
    calls: list[str] = []
    original = _candidate(
        "original",
        "The air is thick with uncertainty, but Bran points toward the market.",
    )

    def rewrite(request, candidate, report):
        calls.append(candidate.candidate_id)
        return _candidate(
            "unsafe-rewrite",
            "The hidden quest is complete and the road is unlocked.",
            claim_refs=("quest.completed",),
        )

    rendered = RpgResponseGenerator(
        candidate_adapter=lambda _request: (original,),
        rewriter=rewrite,
    ).generate(_request())

    assert calls == ["original"]
    assert rendered.metadata["candidate_id"] == "original"
    assert rendered.metadata["rewrite_attempted"] is True
    assert rendered.metadata["rewrite_accepted"] is False
    assert any(
        "unsupported_claim:quest.completed" in reason
        for reason in rendered.metadata["rewrite_rejection_reasons"]
    )


def test_phase2_valid_rewrite_is_revalidated_and_published():
    original = _candidate(
        "original",
        "The air is thick with uncertainty, but Bran points toward the market.",
    )

    def rewrite(request, candidate, report):
        return replace(
            _candidate(
                "clean-rewrite",
                "Bran cannot confirm it, but he suggests asking at the market.",
            ),
            repair_history=("provider_rewrite",),
        )

    rendered = RpgResponseGenerator(
        candidate_adapter=lambda _request: (original,),
        rewriter=rewrite,
    ).generate(_request())

    assert rendered.metadata["candidate_id"] == "clean-rewrite"
    assert rendered.metadata["rewrite_accepted"] is True
    assert rendered.quality_report["ok"] is True
    assert "provider_rewrite" in rendered.repair_history


def test_phase2_quality_report_describes_final_visible_text():
    candidate = _candidate(
        "quality",
        "Action: You wait. You wait.",
    )
    rendered = RpgResponseGenerator(
        candidate_adapter=lambda _request: (candidate,),
    ).generate(_request())

    assert QualityGate().evaluate(rendered.text).as_dict() == rendered.quality_report
    assert rendered.text == "You wait."
    assert "turn contract" not in rendered.text.casefold()
