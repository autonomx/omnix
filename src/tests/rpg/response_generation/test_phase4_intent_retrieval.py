from __future__ import annotations

import pytest

from app.rpg.response_generation.intent_affordance import NarrativeAffordanceClassifier
from app.rpg.response_generation.recovery import LocalRecoveryCoordinator
from app.rpg.response_generation.retrieval import (
    EvidenceRecord,
    LocalKnowledgeRetriever,
    build_retrieval_sources,
)


@pytest.mark.parametrize(
    ("player_input", "expected_affordance"),
    [
        ("Where is the Moonwell?", "entity_search"),
        ("I telephone the king.", "world_equivalent"),
        ("I cast mind reading on the guard.", "analogous_skill"),
        ("Travel to the sealed Royal Vault.", "ask_directions"),
        ("Make him understand.", "clarification"),
        ("As the queen's secret agent, I order him aside.", "unverified_player_claim"),
    ],
)
def test_phase4_classifier_maps_unusual_inputs_to_broad_affordances(
    player_input: str,
    expected_affordance: str,
):
    analysis = NarrativeAffordanceClassifier().classify(
        player_input,
        known_locations={},
        supported_mechanics=(),
    )

    assert any(row.affordance == expected_affordance for row in analysis.hypotheses)
    assert analysis.selected.state_mutation_allowed is False


def test_phase4_low_confidence_input_prefers_clarification_not_generic_fallback():
    analysis = NarrativeAffordanceClassifier().classify("Do the thing.")

    assert analysis.selected.affordance == "inspect_or_clarify"
    assert analysis.selected.ambiguity == "high"
    assert analysis.selected.confidence < 0.5


def test_phase4_local_retrieval_uses_required_source_order_for_equal_matches():
    sources = build_retrieval_sources(
        resolved_turn=[{"evidence_id": "resolved", "content": "Moonwell unknown"}],
        scene=[{"evidence_id": "scene", "content": "Moonwell unknown"}],
        speaker=[{"evidence_id": "speaker", "content": "Moonwell unknown"}],
        journal=[{"evidence_id": "journal", "content": "Moonwell unknown"}],
        lorebook=[{"evidence_id": "lore", "content": "Moonwell unknown"}],
    )

    result = LocalKnowledgeRetriever().retrieve("Moonwell", sources)

    assert [row.evidence_id for row in result.evidence] == [
        "resolved",
        "scene",
        "speaker",
        "journal",
        "lore",
    ]
    assert result.knowledge_status == "known"


def test_phase4_hidden_and_out_of_scope_speaker_evidence_never_reaches_results():
    sources = build_retrieval_sources(
        speaker=[
            EvidenceRecord(
                "bran-visible",
                "speaker",
                "Bran heard a northern caravan rumor.",
                speaker_ids=("npc_bran",),
            ),
            EvidenceRecord(
                "elara-private",
                "speaker",
                "Elara knows the exact location.",
                speaker_ids=("npc_elara",),
            ),
            EvidenceRecord(
                "director-hidden",
                "speaker",
                "The director has scheduled an ambush.",
                visibility="hidden",
            ),
        ]
    )

    result = LocalKnowledgeRetriever().retrieve(
        "northern location ambush",
        sources,
        speaker_id="npc_bran",
    )

    assert [row.evidence_id for row in result.evidence] == ["bran-visible"]
    assert result.hidden_evidence_ids == ("director-hidden",)
    assert "speaker_scope_excluded:elara-private" in result.trace


def test_phase4_aliases_and_conflicting_evidence_are_reported_explicitly():
    sources = build_retrieval_sources(
        lorebook=[
            EvidenceRecord(
                "lore-a",
                "lorebook",
                "The Silver Spring lies north.",
                aliases=("Moonwell",),
                metadata={"subject": "moonwell_direction", "asserted_value": "north"},
            ),
            EvidenceRecord(
                "lore-b",
                "lorebook",
                "An old account places it south.",
                aliases=("Moonwell",),
                metadata={"subject": "moonwell_direction", "asserted_value": "south"},
            ),
        ]
    )

    result = LocalKnowledgeRetriever().retrieve("Moonwell", sources)

    assert result.knowledge_status == "conflicting"
    assert set(result.conflicting_evidence_ids) == {"lore-a", "lore-b"}


def test_phase4_local_recovery_exhausts_local_sources_before_hermes():
    coordinator = LocalRecoveryCoordinator()
    local = coordinator.analyze(
        "Where is the Moonwell?",
        retrieval_sources=build_retrieval_sources(
            journal=[
                EvidenceRecord(
                    "journal-moonwell",
                    "journal",
                    "Elara may recognize the name Moonwell.",
                )
            ]
        ),
    )
    unknown = coordinator.analyze(
        "Where is the Moonwell?",
        retrieval_sources=build_retrieval_sources(),
    )

    assert local.retrieval.local_hit is True
    assert local.needs_hermes is False
    assert local.reason == "local_evidence_sufficient"
    assert unknown.retrieval.knowledge_status == "unknown"
    assert unknown.needs_hermes is True
    assert unknown.state_mutation_allowed is False


def test_phase4_ambiguous_social_input_does_not_trigger_hermes():
    analysis = LocalRecoveryCoordinator().analyze(
        "Make him understand.",
        retrieval_sources=build_retrieval_sources(),
    )

    assert analysis.intent.selected.affordance == "clarification"
    assert analysis.needs_hermes is False
    assert analysis.reason == "clarification_preferred"
