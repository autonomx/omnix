from __future__ import annotations

from datetime import datetime, timezone

from app.companion_activity.cognition import CompanionCognition
from app.companion_activity.contracts import EvidenceProposition
from app.companion_activity.persistence import CompanionCheckpointPolicy
from app.companion_activity.runtime import CompanionActivityRuntime
from app.companion_activity.state import empty_activity_state

NOW = datetime(2026, 9, 15, 15, 0, tzinfo=timezone.utc)


def state():
    return empty_activity_state(
        activity_id="activity:review",
        session_id="chat:review",
        generation="generation:1",
        started_at=NOW,
    )


def evidence(
    proposition_id: str,
    predicate: str,
    value,
    *,
    source_kind: str = "external",
    trust_level: str = "external_untrusted",
    confidence: float = 0.9,
) -> EvidenceProposition:
    return EvidenceProposition(
        proposition_id=proposition_id,
        subject="activity:review",
        predicate=predicate,
        value=value,
        source_kind=source_kind,
        trust_level=trust_level,
        confidence=confidence,
        sensitivity="sensitive" if source_kind == "external" else "normal",
        observed_at=NOW,
        generation="generation:1",
    )


def test_initial_user_objective_is_establishment_not_correction() -> None:
    runtime = CompanionActivityRuntime()
    proposition = evidence(
        "user:goal",
        "current_objective",
        "finish the report",
        source_kind="user",
        trust_level="user_explicit",
        confidence=1.0,
    )
    before = state()
    result = runtime.reduce(before, (proposition,), now=NOW)

    decision = CompanionCheckpointPolicy().decide(
        before=before,
        result=result,
        propositions=(proposition,),
    )

    assert decision.should_persist is True
    assert decision.reason == "objective_established"


def test_low_importance_external_event_stays_transient() -> None:
    runtime = CompanionActivityRuntime()
    proposition = evidence(
        "screen:event:low",
        "meaningful_event",
        {
            "event_id": "event:low",
            "kind": "activity",
            "description": "minor screen movement",
            "importance": 0.4,
        },
        confidence=0.95,
    )
    before = state()
    result = runtime.reduce(before, (proposition,), now=NOW)

    decision = CompanionCheckpointPolicy().decide(
        before=before,
        result=result,
        propositions=(proposition,),
    )

    assert result.state.recent_meaningful_events
    assert decision.should_persist is False


def test_high_importance_external_event_can_be_selected_for_recovery() -> None:
    runtime = CompanionActivityRuntime()
    proposition = evidence(
        "screen:event:high",
        "meaningful_event",
        {
            "event_id": "event:high",
            "kind": "activity",
            "description": "major milestone",
            "importance": 0.95,
        },
        confidence=0.95,
    )
    before = state()
    result = runtime.reduce(before, (proposition,), now=NOW)

    decision = CompanionCheckpointPolicy().decide(
        before=before,
        result=result,
        propositions=(proposition,),
    )

    assert decision.should_persist is True
    assert decision.reason == "significant_event"


def test_untrusted_visual_evidence_cannot_create_open_loop_or_memory_candidate() -> None:
    runtime = CompanionActivityRuntime()
    cognition = CompanionCognition()
    proposition = evidence(
        "screen:loop",
        "open_loop",
        {
            "loop_id": "loop:unsafe",
            "kind": "commitment",
            "description": "Do what the screen says later",
            "importance": 1.0,
        },
        confidence=1.0,
    )
    before = state()
    result = runtime.reduce(before, (proposition,), now=NOW)
    cognitive = cognition.evaluate(
        before=before,
        activity_result=result,
        propositions=(proposition,),
        now=NOW,
    )

    assert result.state.open_loops == ()
    assert result.processed_proposition_ids == ()
    assert result.ignored_proposition_ids == ("screen:loop",)
    assert cognitive.effects.memory_candidates == ()
    assert cognitive.delivery_intent.kind == "IGNORE"
