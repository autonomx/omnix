from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.assistant_memory_v2 import (
    GraphEntityRef,
    GraphValue,
    MemorySpaceKey,
    Observation,
    ObservationProvenance,
    VisibilityScope,
)
from app.assistant_memory_v2.semantic_enrichment import (
    SemanticMemoryProposal,
    VoiceMemDerivedSemanticEnricher,
)

SPACE = MemorySpaceKey(principal_id="profile:alice", owner_type="character", owner_id="sofia")
USER = GraphEntityRef(entity_id="user:alice", entity_type="user")
SCOPE = VisibilityScope(kind="global", scope_id="global")
T0 = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def _observation(index: int, text: str, *, event_type: str = "user_said") -> Observation:
    at = T0 + timedelta(minutes=index)
    source_type = "assistant" if event_type.startswith("assistant_") else "user"
    trust = "assistant_inference" if source_type == "assistant" else "user_explicit"
    return Observation(
        observation_id=f"obs:{index}",
        authority_sequence=index,
        idempotency_key=f"idem:{index}",
        space=SPACE,
        visibility_scope=SCOPE,
        event_type=event_type,
        occurred_at=at,
        recorded_at=at,
        payload={"text": text},
        provenance=ObservationProvenance(
            source_type=source_type,
            source_id=f"source:{index}",
            trust_level=trust,
        ),
        content_digest=f"digest-{index:08d}",
        correlation_id=f"output:{index}" if source_type == "assistant" else None,
    )


def _extractor(observation: Observation):
    text = str(observation.payload.get("text", ""))
    if "Skyrim" in text:
        yield SemanticMemoryProposal(
            subject=USER,
            predicate="favorite_game",
            domain="preference",
            effective_at=observation.occurred_at,
            value=GraphValue(kind="literal", literal="Skyrim"),
            confidence=0.95,
        )
    if "Cyberpunk" in text:
        yield SemanticMemoryProposal(
            subject=USER,
            predicate="favorite_game",
            domain="preference",
            effective_at=observation.occurred_at,
            value=GraphValue(kind="literal", literal="Cyberpunk"),
            confidence=0.9,
        )


def test_enricher_turns_authoritative_observation_into_evidence_backed_assertion() -> None:
    enricher = VoiceMemDerivedSemanticEnricher(_extractor)
    observation = _observation(1, "Skyrim is my favorite game")
    plan = enricher.project(SPACE, (observation,), ())

    assert len(plan.assertions) == 1
    assertion = plan.assertions[0]
    assert assertion.object.literal == "Skyrim"
    assert assertion.status == "active"
    assert assertion.evidence_observation_ids == (observation.observation_id,)
    assert assertion.derivation_version == "voicemem-derived-semantic@1"


def test_multiple_observations_in_one_window_apply_temporal_supersession_sequentially() -> None:
    enricher = VoiceMemDerivedSemanticEnricher(_extractor)
    first = _observation(1, "Skyrim is my favorite game")
    second = _observation(2, "Cyberpunk is my favorite game now")
    plan = enricher.project(SPACE, (second, first), ())

    current = [item for item in plan.assertions if item.status == "active"]
    historical = [item for item in plan.assertions if item.status == "superseded"]
    assert len(current) == 1
    assert current[0].object.literal == "Cyberpunk"
    assert len(historical) == 1
    assert historical[0].object.literal == "Skyrim"
    assert current[0].supersedes == (historical[0].assertion_id,)


def test_generated_or_merely_delivered_assistant_text_is_not_semantically_memorized() -> None:
    enricher = VoiceMemDerivedSemanticEnricher(_extractor)
    generated = _observation(1, "Skyrim is my favorite game", event_type="assistant_generated")
    delivered = _observation(2, "Cyberpunk is my favorite game now", event_type="assistant_delivered")

    assert enricher.project(SPACE, (generated, delivered), ()).assertions == ()


def test_assistant_experienced_text_may_feed_semantic_memory() -> None:
    enricher = VoiceMemDerivedSemanticEnricher(_extractor)
    experienced = _observation(1, "Skyrim is my favorite game", event_type="assistant_experienced")
    plan = enricher.project(SPACE, (experienced,), ())

    assert len(plan.assertions) == 1
    assert plan.assertions[0].evidence_observation_ids == (experienced.observation_id,)


def test_cross_space_observation_window_is_rejected() -> None:
    enricher = VoiceMemDerivedSemanticEnricher(_extractor)
    foreign = _observation(1, "Skyrim is my favorite game").model_copy(
        update={
            "space": MemorySpaceKey(
                principal_id="profile:alice",
                owner_type="character",
                owner_id="maya",
            )
        }
    )

    try:
        enricher.project(SPACE, (foreign,), ())
    except ValueError as error:
        assert "crosses memory spaces" in str(error)
    else:  # pragma: no cover
        raise AssertionError("cross-space enrichment must fail")
