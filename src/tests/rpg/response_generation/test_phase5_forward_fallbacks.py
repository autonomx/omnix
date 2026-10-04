from __future__ import annotations

import pytest

from app.rpg.response_generation.contracts import ResponseMode
from app.rpg.response_generation.fallback_library import (
    DeterministicFallbackLibrary,
    FallbackInput,
)
from app.rpg.response_generation.forward_motion import (
    ForwardMotionPolicy,
    RecoveryHistoryEntry,
    validate_agency,
)
from app.rpg.response_generation.recovery import LocalRecoveryCoordinator
from app.rpg.response_generation.retrieval import EvidenceRecord, build_retrieval_sources


@pytest.mark.parametrize(
    ("player_input", "expected_outcomes"),
    [
        ("Where is the Moonwell?", {"lead", "answer", "uncertainty"}),
        ("I telephone the king.", {"alternative"}),
        ("I cast mind reading on the guard.", {"alternative"}),
        ("Travel to the sealed Royal Vault.", {"lead"}),
        ("Make him understand.", {"clarification"}),
        ("As the queen's secret agent, I order him aside.", {"reaction", "clarification"}),
        ("Do the thing.", {"clarification"}),
    ],
)
def test_phase5_unsupported_inputs_receive_forward_outcomes(
    player_input: str,
    expected_outcomes: set[str],
):
    analysis = LocalRecoveryCoordinator().analyze(
        player_input,
        retrieval_sources=build_retrieval_sources(),
    )
    plan = ForwardMotionPolicy().select(analysis)

    assert plan.outcome in expected_outcomes
    assert plan.state_mutation_allowed is False
    assert plan.starts_path is False
    assert plan.offer_only is True
    assert validate_agency(plan) == ()


def test_phase5_visible_local_evidence_produces_bounded_answer_not_agent_call():
    analysis = LocalRecoveryCoordinator().analyze(
        "Why do caravans avoid the road?",
        retrieval_sources=build_retrieval_sources(
            journal=[
                EvidenceRecord(
                    "journal-road",
                    "journal",
                    "The journal records repeated rockslides on the north road.",
                )
            ]
        ),
    )
    plan = ForwardMotionPolicy().select(analysis)

    assert analysis.needs_hermes is False
    assert plan.strategy == "answer_with_visible_evidence"
    assert plan.outcome == "answer"
    assert plan.requires_player_confirmation is False
    assert plan.answer_evidence_ids == ("journal-road",)


def test_phase5_repeated_recovery_breaks_the_loop():
    analysis = LocalRecoveryCoordinator().analyze(
        "Where is the Moonwell?",
        retrieval_sources=build_retrieval_sources(),
    )
    history = (
        RecoveryHistoryEntry("turn-1", analysis.intent.selected.affordance, "moonwell"),
        RecoveryHistoryEntry("turn-2", analysis.intent.selected.affordance, "moonwell"),
    )

    plan = ForwardMotionPolicy().select(analysis, history=history, target="moonwell")

    assert plan.strategy == "break_recovery_loop"
    assert plan.outcome == "choice"
    assert len(plan.options) >= 2


def test_phase5_resolved_mechanics_are_the_only_recovery_path_allowed_to_mutate():
    analysis = LocalRecoveryCoordinator().analyze(
        "Travel to Westgate.",
        known_locations={"westgate": {"name": "Westgate"}},
        retrieval_sources=build_retrieval_sources(),
    )

    unresolved = ForwardMotionPolicy().select(analysis)
    resolved = ForwardMotionPolicy().select(
        analysis,
        clear_player_intent=True,
        mechanic_resolved=True,
    )

    assert unresolved.state_mutation_allowed is False
    assert resolved.state_mutation_allowed is True
    assert resolved.starts_path is True
    assert resolved.offer_only is False
    assert validate_agency(resolved) == ()


def test_phase5_fallbacks_are_mode_specific_in_world_and_forward_moving():
    analysis = LocalRecoveryCoordinator().analyze(
        "I telephone the king.",
        retrieval_sources=build_retrieval_sources(),
    )
    forward = ForwardMotionPolicy().select(analysis)
    candidate = DeterministicFallbackLibrary().candidate(
        FallbackInput(
            turn_id="turn-phone",
            player_input="I telephone the king.",
            mode=ResponseMode.RECOVERY,
            forward_plan=forward,
        )
    )
    text = candidate.plan.sections[0].text.casefold()

    assert candidate.provider_metadata["grounded_safe_fallback"] is True
    assert "instead" in text
    assert "turn contract" not in text
    assert "unsupported action" not in text
    assert "grounding" not in text
    assert candidate.plan.metadata["takes_player_choice"] is False


def test_phase5_fallback_variation_is_seeded_and_fact_preserving():
    analysis = LocalRecoveryCoordinator().analyze(
        "Where is the Moonwell?",
        retrieval_sources=build_retrieval_sources(),
    )
    forward = ForwardMotionPolicy().select(analysis)
    library = DeterministicFallbackLibrary()

    first = library.candidate(FallbackInput("turn-a", "Where?", ResponseMode.RECOVERY, forward))
    repeat = library.candidate(FallbackInput("turn-a", "Where?", ResponseMode.RECOVERY, forward))
    other = library.candidate(FallbackInput("turn-b", "Where?", ResponseMode.RECOVERY, forward))

    assert first.plan.sections[0].text == repeat.plan.sections[0].text
    assert first.plan.forward_strategy == other.plan.forward_strategy
    assert first.plan.sections[0].claim_refs == other.plan.sections[0].claim_refs == ()


def test_phase5_fallback_answer_uses_only_provided_visible_fact():
    analysis = LocalRecoveryCoordinator().analyze(
        "Why is the road closed?",
        retrieval_sources=build_retrieval_sources(
            scene=[EvidenceRecord("road-sign", "scene", "A sign warns of a washed-out bridge.")]
        ),
    )
    forward = ForwardMotionPolicy().select(analysis)
    candidate = DeterministicFallbackLibrary().candidate(
        FallbackInput(
            turn_id="turn-road",
            player_input="Why is the road closed?",
            mode=ResponseMode.INVESTIGATION,
            forward_plan=forward,
            visible_facts={"answer": "A sign warns that the bridge was washed out."},
            claim_refs=("fact.road_sign",),
        )
    )

    assert candidate.plan.sections[0].text == "A sign warns that the bridge was washed out."
    assert candidate.plan.sections[0].claim_refs == ("fact.road_sign",)
