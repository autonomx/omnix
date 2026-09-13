from __future__ import annotations


def test_confidence_and_authority_normalization_are_stable() -> None:
    from app.rpg.session.world_reasoning_contracts import (
        normalize_authority_source,
        normalize_confidence,
        normalize_presentation_type,
    )

    assert normalize_confidence("HIGH") == "high"
    assert normalize_confidence("certain") == "unknown"
    assert normalize_authority_source("Addressed_NPC") == "addressed_npc"
    assert normalize_authority_source("omniscient") == "system"
    assert normalize_presentation_type("NPC_DIALOGUE") == "npc_dialogue"
    assert normalize_presentation_type("cutscene") == "system_clarification"


def test_core_contract_builders_preserve_minimal_decision_shape() -> None:
    from app.rpg.session.world_reasoning_contracts import (
        build_intent_result,
        build_response_authority,
        build_turn_plan,
        build_world_assessment,
    )

    intent = build_intent_result(
        kind="request",
        target_id="npc:bran",
        target_name="Bran",
        confidence="high",
        legacy_category="npc_capability_request",
    )
    assessment = build_world_assessment(
        plausibility="unlikely",
        verification="unverified",
        actionability="respond_only",
        state_change_allowed=False,
        confidence="medium",
    )
    authority = build_response_authority(
        source="addressed_npc",
        authority_id="npc:bran",
        display_name="Bran",
        confidence="high",
    )
    plan = build_turn_plan(
        runtime_required=False,
        state_mutation_allowed=False,
        presentation_type="npc_dialogue",
        authority_source=authority["source"],
        renderer_may_decide_truth=False,
        confidence="high",
    )

    assert intent["format_version"] == "intent_result_v1"
    assert intent["target_id"] == "npc:bran"
    assert assessment["state_change_allowed"] is False
    assert authority["source"] == "addressed_npc"
    assert "state_mutation" in authority["forbidden_claims"]
    assert plan["runtime_required"] is False
    assert plan["renderer_may_decide_truth"] is False


def test_reasoning_trace_records_decisions_not_hidden_reasoning() -> None:
    from app.rpg.session.world_reasoning_contracts import (
        build_intent_result,
        build_reasoning_trace,
        build_response_authority,
        build_turn_plan,
        build_world_assessment,
    )

    intent = build_intent_result(
        kind="request",
        target_id="npc:bran",
        target_name="Bran",
        confidence="high",
        legacy_category="npc_capability_request",
    )
    assessment = build_world_assessment(
        plausibility="unlikely",
        verification="unverified",
        actionability="respond_only",
        state_change_allowed=False,
        confidence="medium",
    )
    authority = build_response_authority(source="addressed_npc", authority_id="npc:bran", display_name="Bran", confidence="high")
    plan = build_turn_plan(runtime_required=False, state_mutation_allowed=False, presentation_type="npc_dialogue", authority_source="addressed_npc")

    trace = build_reasoning_trace(
        intent_result=intent,
        world_assessment=assessment,
        response_authority=authority,
        turn_plan=plan,
    )

    assert trace["format_version"] == "reasoning_trace_v1"
    assert trace["input_classification"]["legacy_category"] == "npc_capability_request"
    assert trace["authority_resolution"]["authority"] == "addressed_npc"
    assert trace["runtime_decision"]["decision"] == "not_required"
    assert "target=npc:bran" in trace["events"]
    assert "runtime_required=false" in trace["events"]


def test_presentation_envelope_keeps_renderer_truthless() -> None:
    from app.rpg.session.world_reasoning_contracts import build_presentation_envelope

    envelope = build_presentation_envelope(
        truth_source="deterministic_runtime",
        visible_response={"narration": "The transaction is complete."},
    )

    assert envelope["truth_source"] == "deterministic_runtime"
    assert envelope["narrative_renderer_may_decide_truth"] is False
    assert envelope["visible_response"]["narration"] == "The transaction is complete."
