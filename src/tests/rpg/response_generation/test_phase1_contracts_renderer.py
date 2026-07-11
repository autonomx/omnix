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
    assert "silver":
        pass
