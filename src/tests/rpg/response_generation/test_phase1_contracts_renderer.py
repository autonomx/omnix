from __future__ import annotations

import pytest

from app.rpg.response_generation.contracts import (
    AgencyEffect,
    CandidateSource,
    RESPONSE_WORD_BUDGETS,
    ResponseCandidate,
    ResponseMode,
    ResponseRequest,
    SectionType,
    SemanticResponsePlan,
    SemanticSection,
)
from app.rpg.response_generation.orchestration import (
    RpgResponseGenerator,
    build_runtime_shadow_report,
    build_world_scene_shadow_report,
    semantic_plan_from_legacy_payload,
)
from app.rpg.response_generation.renderer import ResponseRenderer


def _plan(mode: ResponseMode) -> SemanticResponsePlan:
    section_type = (
        SectionType.NPC_DIALOGUE
        if mode is ResponseMode.DIALOGUE
        else SectionType.RESULT
        if mode in {ResponseMode.TRANSACTION, ResponseMode.FAILURE}
        else SectionType.NARRATION
    )
    return SemanticResponsePlan(
        mode=mode,
        sections=(
            SemanticSection(
                section_id=f"{mode.value}.primary",
                section_type=section_type,
                speaker_id="npc_bran" if section_type is SectionType.NPC_DIALOGUE else "",
                text=f"A specific {mode.value} response.",
                claim_refs=(f"{mode.value}.resolved",),
            ),
        ),
        forward_strategy="answer_directly",
        agency_effect=AgencyEffect.NONE,
    )


@pytest.mark.parametrize("mode", list(ResponseMode))
def test_phase1_renderer_snapshots_every_response_mode(mode: ResponseMode):
    rendered = ResponseRenderer().render(_plan(mode))

    assert rendered.mode is mode
    assert rendered.word_budget == RESPONSE_WORD_BUDGETS[mode]
    assert rendered.approved_section_ids == (f"{mode.value}.primary",)
    assert rendered.resolved_claim_refs == (f"{mode.value}.resolved",)
    assert mode.value in rendered.text
    assert rendered.delivery_units


def test_phase1_renderer_deduplicates_legacy_action_summaries():
    plan = SemanticResponsePlan(
        mode=ResponseMode.ACTION,
        sections=(
            SemanticSection(
                section_id="narration",
                section_type=SectionType.NARRATION,
                text="You open the weathered door and step inside.",
            ),
            SemanticSection(
                section_id="action",
                section_type=SectionType.ACTION,
                text="You open the weathered door and step inside.",
            ),
            SemanticSection(
                section_id="result",
                section_type=SectionType.RESULT,
                text="The weathered door opens and you step inside.",
            ),
        ),
    )

    rendered = ResponseRenderer().render(plan)

    assert rendered.text.count("weathered door") == 1
    assert len(rendered.approved_section_ids) == 1


def test_phase1_authoritative_deltas_remain_metadata_not_prose():
    plan = _plan(ResponseMode.TRANSACTION)
    rendered = ResponseRenderer().render(
        plan,
        authoritative_deltas={"currency": {"silver": -5}, "inventory": ["room_key"]},
    )

    assert rendered.authoritative_deltas["currency"]["silver"] == -5
    assert "silver" not in rendered.text.casefold()
    assert "room_key" not in rendered.text


def test_phase1_dialogue_renderer_formats_speaker_text_without_debug_labels():
    rendered = ResponseRenderer().render(_plan(ResponseMode.DIALOGUE))

    assert rendered.text.startswith("“")
    assert "npc_bran:" not in rendered.text
    assert "Result:" not in rendered.text


def test_phase1_runtime_and_world_scene_payloads_use_one_semantic_adapter_shape():
    runtime_payload = {
        "source": "provider_runtime_narration",
        "response_mode": "dialogue",
        "narration": "Bran glances toward the stairs.",
        "action": "Bran glances toward the stairs.",
        "npc": {"speaker": "Bran", "line": "Five silver for the night."},
    }
    world_payload = {
        "source": "world_scene_narrator",
        "mode": "dialogue",
        "narration": "Bran glances toward the stairs.",
        "npc_line": "Five silver for the night.",
        "speaker": "Bran",
    }

    runtime_plan = semantic_plan_from_legacy_payload(
        runtime_payload,
        mode=ResponseMode.DIALOGUE,
    )
    world_plan = semantic_plan_from_legacy_payload(
        world_payload,
        mode=ResponseMode.DIALOGUE,
    )

    assert runtime_plan.mode is world_plan.mode is ResponseMode.DIALOGUE
    assert {section.section_type for section in runtime_plan.sections} == {
        SectionType.NARRATION,
        SectionType.ACTION,
        SectionType.NPC_DIALOGUE,
    }
    assert {section.section_type for section in world_plan.sections} == {
        SectionType.NARRATION,
        SectionType.NPC_DIALOGUE,
    }


def test_phase1_canonical_generator_owns_final_visible_assembly():
    candidate = ResponseCandidate(
        candidate_id="candidate-1",
        plan=_plan(ResponseMode.ACTION),
        source=CandidateSource.DETERMINISTIC,
    )
    generator = RpgResponseGenerator(candidate_adapter=lambda _request: (candidate,))
    request = ResponseRequest(
        turn_id="turn-1",
        player_input="Open the door.",
        authoritative_turn_result={"state_delta": {"door_open": True}},
    )

    rendered = generator.generate(request)

    assert rendered.text == "A specific action response."
    assert rendered.metadata["candidate_id"] == "candidate-1"
    assert rendered.metadata["candidate_source"] == "deterministic"
    assert rendered.authoritative_deltas == {"door_open": True}


def test_phase1_shadow_reports_preserve_legacy_text_and_do_not_mutate_state():
    payload = {
        "source": "provider_runtime_narration",
        "response_mode": "action",
        "narration": "You open the door.",
        "action": "You open the door.",
    }
    runtime_report = build_runtime_shadow_report(
        turn_id="turn-runtime",
        player_input="Open the door.",
        runtime_payload=payload,
        authoritative_turn_result={"state_delta": {"door_open": True}},
        legacy_visible_text="You open the door. Result: You open the door.",
    )
    world_report = build_world_scene_shadow_report(
        turn_id="turn-world",
        player_input="Open the door.",
        world_scene_payload=payload,
        authoritative_turn_result={"state_delta": {"door_open": True}},
        legacy_visible_text="You open the door.",
    )

    assert runtime_report["authoritative_state_unchanged"] is True
    assert world_report["authoritative_state_unchanged"] is True
    assert runtime_report["canonical_visible_text"] == "You open the door."
    assert world_report["canonical_visible_text"] == "You open the door."
