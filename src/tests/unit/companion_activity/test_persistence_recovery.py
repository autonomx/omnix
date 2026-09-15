from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.companion_activity.contracts import EvidenceProposition
from app.companion_activity.persistence import (
    CompanionActivityCheckpoint,
    CompanionActivityRecovery,
    CompanionCheckpointPolicy,
    InMemoryCompanionActivityCheckpointStore,
    build_activity_checkpoint,
)
from app.companion_activity.runtime import CompanionActivityRuntime
from app.companion_activity.state import ActivityTransitionCandidate, empty_activity_state

NOW = datetime(2026, 9, 15, 11, 0, tzinfo=timezone.utc)


def evidence(
    proposition_id: str,
    predicate: str,
    value,
    *,
    source_kind: str = "external",
    trust_level: str = "external_untrusted",
    confidence: float = 0.9,
    seconds: int = 0,
) -> EvidenceProposition:
    return EvidenceProposition(
        proposition_id=proposition_id,
        subject="activity:1",
        predicate=predicate,
        value=value,
        source_kind=source_kind,
        trust_level=trust_level,
        confidence=confidence,
        sensitivity="sensitive" if source_kind == "external" else "normal",
        observed_at=NOW + timedelta(seconds=seconds),
    )


def initial_state():
    return empty_activity_state(
        activity_id="activity:1",
        session_id="chat:1",
        started_at=NOW,
        character_id="sofia",
        generation="generation:1",
    )


def test_checkpoint_policy_ignores_non_boundary_or_half_confirmed_state() -> None:
    runtime = CompanionActivityRuntime()
    before = initial_state()
    proposition = evidence("screen:objective:1", "current_objective", "beat Malenia")
    half = runtime.reduce(before, (proposition,), now=NOW)
    assert half.state.field("current_objective") is None
    assert half.state.pending_transitions

    decision = CompanionCheckpointPolicy().decide(
        before=before,
        result=half,
        propositions=(proposition,),
    )
    assert decision.should_persist is False


def test_objective_and_user_correction_are_checkpoint_boundaries() -> None:
    runtime = CompanionActivityRuntime()
    before = initial_state()
    objective_evidence = (
        evidence("screen:1", "current_objective", "beat Malenia"),
        evidence("screen:2", "current_objective", "beat Malenia", seconds=1),
    )
    established = runtime.reduce(
        before,
        objective_evidence,
        now=NOW + timedelta(seconds=1),
    )
    objective_decision = CompanionCheckpointPolicy().decide(
        before=before,
        result=established,
        propositions=objective_evidence,
    )
    assert objective_decision.should_persist is True
    assert objective_decision.reason == "objective_established"

    correction = evidence(
        "user:correction",
        "current_objective",
        "farm runes",
        source_kind="user",
        trust_level="user_explicit",
        confidence=1.0,
        seconds=2,
    )
    corrected = runtime.reduce(
        established.state,
        (correction,),
        now=NOW + timedelta(seconds=2),
    )
    correction_decision = CompanionCheckpointPolicy().decide(
        before=established.state,
        result=corrected,
        propositions=(correction,),
    )
    assert correction_decision.should_persist is True
    assert correction_decision.reason == "user_correction"


def test_checkpoint_drops_pending_hysteresis_and_defaults_sensitive() -> None:
    pending = ActivityTransitionCandidate(
        field_name="strategy",
        value="bleed build",
        authority_source="single_perception",
        confidence=0.8,
        proposition_ids=("screen:strategy:1",),
        first_seen_at=NOW,
        last_seen_at=NOW,
        confirmation_count=1,
    )
    state = initial_state().model_copy(update={"pending_transitions": (pending,)})

    checkpoint = build_activity_checkpoint(
        state=state,
        reason="manual",
        created_at=NOW,
        source_proposition_ids=("screen:strategy:1",),
    )

    assert checkpoint.sensitivity == "sensitive"
    assert checkpoint.state.pending_transitions == ()
    assert checkpoint.source_proposition_ids == ("screen:strategy:1",)

    invalid = checkpoint.model_dump()
    invalid["sensitivity"] = "normal"
    with pytest.raises(ValidationError):
        CompanionActivityCheckpoint.model_validate(invalid)


def test_in_memory_store_is_bounded_and_idempotent_for_same_revision_reason() -> None:
    store = InMemoryCompanionActivityCheckpointStore(maximum_per_session=2)
    state = initial_state()
    first = build_activity_checkpoint(state=state, reason="manual", created_at=NOW)
    store.save(first)
    store.save(first)

    second_state = state.model_copy(update={"revision": 1})
    second = build_activity_checkpoint(
        state=second_state,
        reason="major_progress",
        created_at=NOW + timedelta(seconds=1),
    )
    third_state = state.model_copy(update={"revision": 2})
    third = build_activity_checkpoint(
        state=third_state,
        reason="significant_event",
        created_at=NOW + timedelta(seconds=2),
    )
    store.save(second)
    store.save(third)

    assert store.latest("chat:1") == third
    assert store.latest("chat:1", activity_id="activity:1") == third
    assert len(store._by_session["chat:1"]) == 2


def test_recovery_reduces_fresh_user_evidence_over_restored_projection() -> None:
    runtime = CompanionActivityRuntime()
    established = runtime.reduce(
        initial_state(),
        (
            evidence("screen:1", "current_objective", "beat Malenia"),
            evidence("screen:2", "current_objective", "beat Malenia", seconds=1),
        ),
        now=NOW + timedelta(seconds=1),
    ).state
    checkpoint = build_activity_checkpoint(
        state=established,
        reason="objective_established",
        created_at=NOW + timedelta(seconds=1),
    )
    fresh = evidence(
        "user:fresh",
        "current_objective",
        "farm runes",
        source_kind="user",
        trust_level="user_explicit",
        confidence=1.0,
        seconds=10,
    )

    recovered = CompanionActivityRecovery(runtime).recover(
        checkpoint,
        (fresh,),
        now=NOW + timedelta(seconds=10),
    )

    assert recovered.state.field("current_objective").value == "farm runes"
    assert recovered.state.field("current_objective").authority_source == "user_explicit"


def test_half_confirmed_pre_restart_evidence_cannot_complete_after_restore() -> None:
    runtime = CompanionActivityRuntime()
    before = initial_state()
    half = runtime.reduce(
        before,
        (evidence("screen:strategy:1", "strategy", "bleed build"),),
        now=NOW,
    )
    assert half.state.pending_transitions

    checkpoint = build_activity_checkpoint(
        state=half.state,
        reason="manual",
        created_at=NOW,
    )
    assert checkpoint.state.pending_transitions == ()

    recovered = CompanionActivityRecovery(runtime).recover(
        checkpoint,
        (evidence("screen:strategy:2", "strategy", "bleed build", seconds=5),),
        now=NOW + timedelta(seconds=5),
    )

    assert recovered.state.field("strategy") is None
    pending = [item for item in recovered.state.pending_transitions if item.field_name == "strategy"]
    assert len(pending) == 1
    assert pending[0].confirmation_count == 1
