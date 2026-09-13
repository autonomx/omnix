from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.assistant_memory_v2 import (
    SYSTEM_MEMORY_OWNER_ID,
    AffectObservation,
    ConsolidationReceipt,
    CutoverReadiness,
    GraphAssertion,
    GraphEntityRef,
    GraphValue,
    MemoryAuthorityEpoch,
    MemoryGrant,
    MemorySpaceKey,
    MemoryWatermarks,
    Observation,
    ObservationDisposition,
    ObservationProvenance,
    RelationshipMetric,
    RelationshipState,
    RetrievalQuery,
    VisibilityScope,
)

NOW = datetime(2026, 9, 13, 20, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 9, 13, 20, 1, tzinfo=timezone.utc)


def sofia_space(principal_id: str = "profile:alice") -> MemorySpaceKey:
    return MemorySpaceKey(
        principal_id=principal_id,
        owner_type="character",
        owner_id="sofia",
    )


def project_scope(project_id: str = "project:omnix") -> VisibilityScope:
    return VisibilityScope(kind="project", scope_id=project_id)


def provenance() -> ObservationProvenance:
    return ObservationProvenance(
        source_type="user",
        source_id="msg:101",
        trust_level="user_explicit",
        session_id="chat:one",
        turn_id="turn:10",
        message_id="msg:101",
    )


def observation(**overrides) -> Observation:
    values = {
        "observation_id": "obs:101",
        "authority_sequence": 101,
        "idempotency_key": "chat:one:turn:10:user-final",
        "space": sofia_space(),
        "visibility_scope": project_scope(),
        "event_type": "user_said",
        "occurred_at": NOW,
        "recorded_at": NOW,
        "payload": {"text": "Cyberpunk is probably my favorite now."},
        "provenance": provenance(),
    }
    values.update(overrides)
    return Observation(**values)


def test_memory_space_is_owner_identity_not_workspace_or_project_fragmentation():
    space = sofia_space()
    first_scope = project_scope("project:omnix")
    second_scope = project_scope("project:rpg")

    assert space == sofia_space()
    assert first_scope != second_scope
    assert "workspace_id" not in MemorySpaceKey.model_fields
    assert "project_id" not in MemorySpaceKey.model_fields
    assert set(MemorySpaceKey.model_fields) == {"principal_id", "owner_type", "owner_id"}


def test_character_and_system_memory_owners_cannot_alias():
    system = MemorySpaceKey(
        principal_id="profile:alice",
        owner_type="system",
        owner_id=SYSTEM_MEMORY_OWNER_ID,
    )
    assert system.owner_id == SYSTEM_MEMORY_OWNER_ID

    with pytest.raises(ValidationError):
        MemorySpaceKey(
            principal_id="profile:alice",
            owner_type="character",
            owner_id=SYSTEM_MEMORY_OWNER_ID,
        )

    with pytest.raises(ValidationError):
        MemorySpaceKey(
            principal_id="profile:alice",
            owner_type="system",
            owner_id="sofia",
        )


def test_same_character_is_isolated_between_principals():
    assert sofia_space("profile:alice") != sofia_space("profile:bob")


def test_observation_is_append_only_evidence_with_sequence_and_idempotency_identity():
    item = observation()

    assert item.authority_sequence == 101
    assert item.idempotency_key == "chat:one:turn:10:user-final"
    assert item.event_type == "user_said"
    with pytest.raises(ValidationError):
        item.payload = {"text": "rewritten"}  # type: ignore[misc]


def test_governance_revocation_is_separate_from_observation_mutation():
    item = observation()
    disposition = ObservationDisposition(
        observation_id=item.observation_id,
        state="purged",
        authority_sequence=500,
        changed_at=LATER,
        reason="user requested erasure",
        actor_id="profile:alice",
    )

    assert disposition.observation_id == item.observation_id
    assert disposition.state == "purged"
    assert item.payload["text"].startswith("Cyberpunk")


def test_voice_experience_boundaries_are_first_class_observation_types():
    generated = observation(
        observation_id="obs:generated",
        authority_sequence=102,
        idempotency_key="output:1:generated",
        event_type="assistant_generated",
        payload={"text": "Sentence one. Sentence two. Sentence three."},
    )
    experienced = observation(
        observation_id="obs:experienced",
        authority_sequence=103,
        idempotency_key="output:1:experienced",
        event_type="assistant_experienced",
        payload={"text": "Sentence one. Sen", "rendered_samples": 41200},
    )

    assert generated.event_type != experienced.event_type
    assert generated.payload["text"] != experienced.payload["text"]


def test_graph_assertions_require_evidence_and_valid_temporal_intervals():
    subject = GraphEntityRef(entity_id="profile:alice", entity_type="user")
    value = GraphValue(kind="literal", literal="Cyberpunk")

    assertion = GraphAssertion(
        assertion_id="assert:favorite-game:2",
        space=sofia_space(),
        visibility_scopes=(project_scope(),),
        subject=subject,
        predicate="favorite_game",
        object=value,
        domain="preference",
        confidence=0.88,
        valid_from=NOW,
        evidence_observation_ids=("obs:101",),
        derivation_version="consolidator:v2-alpha",
        supersedes=("assert:favorite-game:1",),
    )
    assert assertion.evidence_observation_ids == ("obs:101",)
    assert assertion.supersedes == ("assert:favorite-game:1",)

    with pytest.raises(ValidationError):
        GraphAssertion(
            assertion_id="assert:no-evidence",
            space=sofia_space(),
            visibility_scopes=(project_scope(),),
            subject=subject,
            predicate="favorite_game",
            object=value,
            domain="preference",
            confidence=0.5,
            derivation_version="consolidator:v2-alpha",
        )

    with pytest.raises(ValidationError):
        GraphAssertion(
            assertion_id="assert:bad-interval",
            space=sofia_space(),
            visibility_scopes=(project_scope(),),
            subject=subject,
            predicate="favorite_game",
            object=value,
            domain="preference",
            confidence=0.5,
            valid_from=LATER,
            valid_until=NOW,
            evidence_observation_ids=("obs:101",),
            derivation_version="consolidator:v2-alpha",
        )


def test_relationship_metrics_are_internal_and_prompt_interpretation_is_explicit():
    metric = RelationshipMetric(
        name="familiarity",
        value=0.87,
        confidence=0.81,
        evidence_observation_ids=("obs:1", "obs:2"),
    )
    relationship = RelationshipState(
        relationship_id="rel:sofia:alice",
        space=sofia_space(),
        subject=GraphEntityRef(entity_id="character:sofia", entity_type="character"),
        counterpart=GraphEntityRef(entity_id="profile:alice", entity_type="user"),
        metrics=(metric,),
        prompt_interpretation=(
            "The relationship is highly familiar; the user responds well to playful "
            "technical discussion."
        ),
        evidence_observation_ids=("obs:1", "obs:2"),
        derivation_version="relationship:v1",
    )

    assert relationship.metrics[0].value == 0.87
    assert "0.87" not in relationship.prompt_interpretation


def test_affect_requires_timed_evidence_and_does_not_imply_current_state():
    affect = AffectObservation(
        affect_id="affect:184",
        space=sofia_space(),
        source_observation_id="obs:184",
        source="acoustic",
        observed_at=NOW,
        valence=-0.4,
        arousal=0.7,
        emotion_distribution={"frustrated": 0.81, "neutral": 0.19},
        confidence=0.81,
        model_version="affect-fusion:v1",
    )
    assert affect.observed_at == NOW
    assert affect.source_observation_id == "obs:184"

    with pytest.raises(ValidationError):
        AffectObservation(
            affect_id="affect:empty",
            space=sofia_space(),
            source_observation_id="obs:185",
            source="acoustic",
            observed_at=NOW,
            confidence=0.2,
            model_version="affect-fusion:v1",
        )


def test_memory_grants_federate_read_access_without_copy_or_write_authority():
    grant = MemoryGrant(
        grant_id="grant:system-to-sofia",
        source_space=MemorySpaceKey(
            principal_id="profile:alice",
            owner_type="system",
            owner_id=SYSTEM_MEMORY_OWNER_ID,
        ),
        target_space=sofia_space(),
        allowed_domains=("fact", "preference"),
        max_sensitivity="normal",
        created_by="profile:alice",
        created_at=NOW,
    )

    assert grant.access == "read"
    assert "write" not in str(MemoryGrant.model_fields["access"].annotation)

    with pytest.raises(ValidationError):
        MemoryGrant(
            grant_id="grant:self",
            source_space=sofia_space(),
            target_space=sofia_space(),
            allowed_domains=("fact",),
            created_by="profile:alice",
            created_at=NOW,
        )


def test_retrieval_is_read_only_by_contract_for_partial_and_final_turns():
    partial = RetrievalQuery(
        query_id="query:partial",
        space=sofia_space(),
        visible_scopes=(project_scope(),),
        text="what was that game I liked",
        authority="partial",
        as_of=NOW,
    )
    final = partial.model_copy(update={"query_id": "query:final", "authority": "final"})

    assert partial.deadline_ms == 50.0
    assert partial.authority == "partial"
    assert final.authority == "final"
    assert "allow_mutation" not in RetrievalQuery.model_fields
    assert "write" not in RetrievalQuery.model_fields


def test_consolidation_receipt_is_watermarked_versioned_and_replay_addressable():
    receipt = ConsolidationReceipt(
        receipt_id="receipt:1",
        space=sofia_space(),
        input_observation_from=101,
        input_observation_through=110,
        consolidator_version="consolidator:v2-alpha",
        schema_version="memory-v2@1",
        provider_id="local",
        model_id="qwen",
        created_assertion_ids=("assert:1",),
        superseded_assertion_ids=("assert:0",),
        resulting_graph_revision=7,
        idempotency_key="consolidate:sofia:101-110:v2-alpha",
        started_at=NOW,
        completed_at=LATER,
    )

    assert receipt.input_observation_through == 110
    assert receipt.resulting_graph_revision == 7

    invalid = receipt.model_dump()
    invalid["input_observation_from"] = 110
    invalid["input_observation_through"] = 101
    with pytest.raises(ValidationError):
        ConsolidationReceipt(**invalid)


def test_cutover_epoch_rejects_v2_until_all_watermarks_and_quality_gates_pass():
    caught_up = MemoryWatermarks(
        authoritative_event=500,
        observation=500,
        consolidation=500,
        graph_revision=42,
        index_graph_revision=42,
    )
    ready = CutoverReadiness(
        watermarks=caught_up,
        graph_validation_passed=True,
        shadow_quality_passed=True,
        indexes_caught_up=True,
        ready=True,
    )
    epoch = MemoryAuthorityEpoch(
        epoch=2,
        authority="v2",
        previous_epoch=1,
        activated_at=NOW,
        readiness=ready,
        activated_by="migration:memory-v2",
    )
    assert epoch.authority == "v2"

    with pytest.raises(ValidationError):
        MemoryAuthorityEpoch(
            epoch=2,
            authority="v2",
            previous_epoch=1,
            activated_at=NOW,
            activated_by="migration:memory-v2",
        )

    with pytest.raises(ValidationError):
        CutoverReadiness(
            watermarks=MemoryWatermarks(
                authoritative_event=500,
                observation=499,
                consolidation=499,
                graph_revision=42,
                index_graph_revision=42,
            ),
            graph_validation_passed=True,
            shadow_quality_passed=True,
            indexes_caught_up=True,
            ready=True,
        )
