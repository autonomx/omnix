from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.assistant_memory_v2 import (
    GraphAssertion,
    GraphEntityRef,
    GraphValue,
    MemorySpaceKey,
    Observation,
    ObservationProvenance,
    VisibilityScope,
)
from app.assistant_memory_v2.temporal import TemporalClaim, apply_temporal_claim

SPACE = MemorySpaceKey(principal_id="profile:alice", owner_type="character", owner_id="sofia")
USER = GraphEntityRef(entity_id="user:alice", entity_type="user")
SCOPE = VisibilityScope(kind="global", scope_id="global")
T0 = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def _observation(index: int, at: datetime) -> Observation:
    return Observation(
        observation_id=f"obs:{index}",
        authority_sequence=index,
        idempotency_key=f"idem:{index}",
        space=SPACE,
        visibility_scope=SCOPE,
        event_type="user_said",
        occurred_at=at,
        recorded_at=at,
        payload={"text": f"turn {index}"},
        provenance=ObservationProvenance(
            source_type="user",
            source_id="user:alice",
            trust_level="user_explicit",
        ),
        content_digest=f"digest-{index:08d}",
    )


def _current(value: str, *, at: datetime = T0, assertion_id: str = "current") -> GraphAssertion:
    return GraphAssertion(
        assertion_id=assertion_id,
        space=SPACE,
        visibility_scopes=(SCOPE,),
        subject=USER,
        predicate="favorite_game",
        object=GraphValue(kind="literal", literal=value),
        domain="preference",
        confidence=0.95,
        valid_from=at,
        evidence_observation_ids=("obs:seed",),
        derivation_version="seed@1",
    )


def _claim(value: str, at: datetime, *, confidence: float = 1.0, single_valued: bool = True):
    return TemporalClaim(
        subject=USER,
        predicate="favorite_game",
        value=GraphValue(kind="literal", literal=value),
        domain="preference",
        effective_at=at,
        confidence=confidence,
        single_valued=single_valued,
    )


def test_strong_newer_single_value_supersedes_prior_current_belief() -> None:
    old = _current("Skyrim")
    at = T0 + timedelta(days=1)
    plan = apply_temporal_claim(SPACE, _observation(2, at), (old,), _claim("Cyberpunk", at))

    assert len(plan.assertions) == 2
    prior = next(item for item in plan.assertions if item.assertion_id == old.assertion_id)
    current = next(item for item in plan.assertions if item.assertion_id != old.assertion_id)
    assert prior.status == "superseded"
    assert prior.valid_until == at
    assert current.status == "active"
    assert current.supersedes == (old.assertion_id,)
    assert current.object.literal == "Cyberpunk"


def test_weak_conflict_is_disputed_without_overwriting_current_belief() -> None:
    old = _current("Skyrim")
    at = T0 + timedelta(hours=1)
    plan = apply_temporal_claim(
        SPACE,
        _observation(2, at),
        (old,),
        _claim("Cyberpunk", at, confidence=0.4),
    )

    assert len(plan.assertions) == 1
    disputed = plan.assertions[0]
    assert disputed.status == "disputed"
    assert disputed.contradicted_by == (old.assertion_id,)
    assert old.status == "active"


def test_out_of_order_claim_becomes_bounded_history_not_current_state() -> None:
    current = _current("Cyberpunk", at=T0 + timedelta(days=2))
    historical_at = T0
    plan = apply_temporal_claim(
        SPACE,
        _observation(3, historical_at),
        (current,),
        _claim("Skyrim", historical_at),
    )

    assert len(plan.assertions) == 1
    historical = plan.assertions[0]
    assert historical.status == "superseded"
    assert historical.valid_from == historical_at
    assert historical.valid_until == current.valid_from
    assert current.status == "active"


def test_same_value_reinforces_evidence_instead_of_creating_duplicate() -> None:
    old = _current("Skyrim")
    at = T0 + timedelta(hours=1)
    plan = apply_temporal_claim(SPACE, _observation(4, at), (old,), _claim("Skyrim", at))

    assert len(plan.assertions) == 1
    reinforced = plan.assertions[0]
    assert reinforced.assertion_id == old.assertion_id
    assert reinforced.status == "active"
    assert reinforced.revision == old.revision + 1
    assert set(reinforced.evidence_observation_ids) == {"obs:seed", "obs:4"}


def test_explicit_retraction_closes_current_interval_without_replacement() -> None:
    old = _current("Skyrim")
    at = T0 + timedelta(hours=1)
    claim = TemporalClaim(
        subject=USER,
        predicate="favorite_game",
        value=GraphValue(kind="literal", literal="Skyrim"),
        domain="preference",
        effective_at=at,
        operation="retract",
    )
    plan = apply_temporal_claim(SPACE, _observation(5, at), (old,), claim)

    assert len(plan.assertions) == 1
    retracted = plan.assertions[0]
    assert retracted.status == "retracted"
    assert retracted.valid_until == at
    assert "obs:5" in retracted.evidence_observation_ids


def test_multi_valued_claim_does_not_supersede_existing_value() -> None:
    old = _current("Skyrim")
    at = T0 + timedelta(hours=1)
    plan = apply_temporal_claim(
        SPACE,
        _observation(6, at),
        (old,),
        _claim("Baldur's Gate", at, single_valued=False),
    )

    assert len(plan.assertions) == 1
    added = plan.assertions[0]
    assert added.status == "active"
    assert added.supersedes == ()
    assert old.status == "active"
