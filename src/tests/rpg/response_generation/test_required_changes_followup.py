from __future__ import annotations

from app.rpg.response_generation.contracts import (
    CandidateSource,
    ResponseCandidate,
    ResponseMode,
    ResponseRequest,
    SectionType,
    SemanticResponsePlan,
    SemanticSection,
)
from app.rpg.response_generation.eligibility import EligibilityPolicy, eligibility_reasons
from app.rpg.response_generation.strict_pipeline import StrictRpgProductionResponsePipeline


def _candidate(
    text: str,
    *,
    claim_refs: tuple[str, ...] = (),
    soft_truth_refs: tuple[str, ...] = (),
) -> ResponseCandidate:
    return ResponseCandidate(
        candidate_id="followup-candidate",
        source=CandidateSource.PROVIDER,
        current_turn_relevance=1.0,
        forward_motion=1.0,
        specificity=1.0,
        naturalness=1.0,
        plan=SemanticResponsePlan(
            mode=ResponseMode.ACTION,
            sections=(
                SemanticSection(
                    section_id="followup.section",
                    section_type=SectionType.RESULT,
                    text=text,
                    claim_refs=claim_refs,
                    soft_truth_refs=soft_truth_refs,
                    metadata={"factual": True},
                ),
            ),
        ),
    )


def _request(**overrides) -> ResponseRequest:
    result = {
        "strict_claim_refs": True,
        "allowed_claim_refs": ["currency.silver", "turn.resolved"],
        "claim_records": [
            {
                "claim_ref": "currency.silver",
                "claim_type": "currency_delta",
                "value": -5,
                "visibility": "player_visible",
            }
        ],
        **overrides,
    }
    return ResponseRequest(
        turn_id="followup-turn",
        player_input="Pay for the room.",
        authoritative_turn_result=result,
        feature_flags={"strict_claim_refs": True},
    )


def test_typed_currency_value_mismatch_is_rejected():
    evaluated = EligibilityPolicy().evaluate(
        _candidate("Bran gives you 100 gold.", claim_refs=("currency.silver",)),
        _request(),
    )

    assert evaluated.eligible is False
    assert "typed_claim_value_mismatch:followup.section:currency" in eligibility_reasons(
        evaluated
    )


def test_matching_typed_currency_value_is_eligible():
    evaluated = EligibilityPolicy().evaluate(
        _candidate("You pay five silver.", claim_refs=("currency.silver",)),
        _request(),
    )

    assert evaluated.eligible is True


def test_unapproved_hermes_inference_cannot_satisfy_grounding():
    evaluated = EligibilityPolicy().evaluate(
        _candidate(
            "The hidden quest is complete.",
            soft_truth_refs=("hermes.inference.0",),
        ),
        _request(allowed_claim_refs=[]),
    )

    assert evaluated.eligible is False
    assert any(
        reason.startswith("unapproved_hermes_soft_truth:")
        for reason in eligibility_reasons(evaluated)
    )


def test_prepare_generation_inputs_runs_before_provider_generation():
    prepared = StrictRpgProductionResponsePipeline().prepare_generation_inputs(
        player_input="Where is the Moonwell?",
        simulation_state={
            "session_id": "followup-session",
            "scene_id": "abbey-yard",
            "response_retrieval_sources": {
                "lorebook": [
                    {
                        "evidence_id": "lore.moonwell",
                        "content": "The Moonwell lies beneath the eastern abbey.",
                        "visibility": "player_visible",
                        "confidence": 1.0,
                    }
                ]
            },
        },
        turn_contract={
            "turn_id": "followup-context-turn",
            "resolver_status": "unresolved",
            "recovery_needed": True,
            "response_mode": "recovery",
        },
    )

    brief = prepared["turn_contract"]["narration_brief"]
    assert brief["must_answer"] == "Where is the Moonwell?"
    assert brief["selected_affordance"]
    assert brief["forward_strategy"]
    assert brief["evidence"][0]["evidence_id"] == "lore.moonwell"
    assert prepared["simulation_state"]["runtime_settings"][
        "canonical_context_compiled_before_generation"
    ] is True


def test_public_apply_turn_wrapper_canonicalizes_early_return():
    from app.rpg.session import runtime_part39

    payload = runtime_part39.apply_turn(
        "followup-session",
        "Bran, join me.",
        _base_apply_turn=lambda *args, **kwargs: {
            "ok": True,
            "narration": "Bran joins your party.",
            "npc": {"speaker": "Bran", "line": "I am with you."},
            "turn_contract": {
                "turn_id": "followup-early-turn",
                "ok": True,
                "action_type": "companion_acceptance",
                "semantic_family": "social",
                "resolved_result": {
                    "ok": True,
                    "action_type": "companion_acceptance",
                    "summary": "Bran joins the party.",
                },
            },
            "simulation_state": {
                "session_id": "followup-session",
                "scene_id": "tavern",
                "response_rollout_stage": "canonical_default",
            },
            "result": {
                "ok": True,
                "narration": "Bran joins your party.",
                "npc": {"speaker": "Bran", "line": "I am with you."},
                "mechanic_resolved": True,
                "allowed_speakers": ["Bran"],
            },
        },
    )

    narration_payload = payload["narration_payload"]
    assert narration_payload["canonical_response_source"] == "rpg_response_generator_v1"
    assert narration_payload["canonical_response"]["quality_report"]["ok"] is True
    assert narration_payload["canonical_response"]["developer_trace"]["quality"]["ok"] is True
    assert payload["presentation_narration_selection"]["source"] == "canonical_runtime_response"
