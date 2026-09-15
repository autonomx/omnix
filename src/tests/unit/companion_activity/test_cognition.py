from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.companion_activity.cognition import CompanionCognition
from app.companion_activity.contracts import EvidenceProposition
from app.companion_activity.runtime import CompanionActivityRuntime
from app.companion_activity.state import empty_activity_state

NOW = datetime(2026, 9, 15, 0, 0, tzinfo=timezone.utc)


def evidence(
    proposition_id: str,
    predicate: str,
    value,
    *,
    source_kind: str = "external",
    trust_level: str = "external_untrusted",
    confidence: float = 0.9,
    sensitivity: str = "normal",
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
        sensitivity=sensitivity,
        observed_at=NOW + timedelta(seconds=seconds),
    )


def initial_state():
    return empty_activity_state(
        activity_id="activity:1",
        session_id="chat:1",
        character_id="sofia",
        started_at=NOW,
    )


def test_boss_death_can_update_state_create_memory_and_react_in_same_cycle() -> None:
    runtime = CompanionActivityRuntime()
    cognition = CompanionCognition()
    before = initial_state()
    propositions = (
        evidence(
            "telemetry:attempt",
            "attempt_count",
            7,
            source_kind="telemetry",
            trust_level="system_trusted",
            confidence=1.0,
        ),
        evidence(
            "screen:death",
            "meaningful_event",
            {"event_id": "death:7", "kind": "failure", "description": "Boss attempt ended"},
            confidence=0.92,
            sensitivity="sensitive",
        ),
    )
    activity = runtime.reduce(before, propositions, now=NOW)
    result = cognition.evaluate(
        before=before,
        activity_result=activity,
        propositions=propositions,
        now=NOW,
    )

    assert "attempt_count" in result.effects.activity_change_fields
    assert any(item.kind == "episode" for item in result.effects.memory_candidates)
    memory = next(item for item in result.effects.memory_candidates if item.kind == "episode")
    assert memory.trust_level == "external_untrusted"
    assert memory.sensitivity == "sensitive"
    assert result.delivery_intent.kind == "REACT"
    assert result.delivery_intent.grounding_proposition_ids == ("screen:death",)


def test_ignore_means_say_nothing_not_learn_nothing() -> None:
    runtime = CompanionActivityRuntime()
    cognition = CompanionCognition()
    established = runtime.reduce(
        initial_state(),
        (
            evidence("screen:1", "current_objective", "beat Malenia"),
            evidence("screen:2", "current_objective", "beat Malenia", seconds=1),
        ),
        now=NOW + timedelta(seconds=1),
    ).state
    correction = evidence(
        "user:correction",
        "current_objective",
        "farm runes",
        source_kind="user",
        trust_level="user_explicit",
        confidence=1.0,
        seconds=2,
    )
    activity = runtime.reduce(
        established,
        (correction,),
        now=NOW + timedelta(seconds=2),
    )
    result = cognition.evaluate(
        before=established,
        activity_result=activity,
        propositions=(correction,),
        now=NOW + timedelta(seconds=2),
    )

    assert result.delivery_intent.kind == "IGNORE"
    assert result.effects.activity_change_fields == ("current_objective",)
    assert any(item.kind == "correction" for item in result.effects.memory_candidates)
    assert activity.state.field("current_objective").value == "farm runes"


def test_warning_intent_does_not_require_activity_field_mutation() -> None:
    runtime = CompanionActivityRuntime()
    cognition = CompanionCognition()
    before = initial_state()
    warning = evidence(
        "runtime:danger",
        "destructive_risk",
        "About to delete unsaved work",
        source_kind="runtime",
        trust_level="system_trusted",
        confidence=0.98,
    )
    activity = runtime.reduce(before, (warning,), now=NOW)
    result = cognition.evaluate(
        before=before,
        activity_result=activity,
        propositions=(warning,),
        now=NOW,
    )

    assert result.effects.activity_change_fields == ()
    assert result.delivery_intent.kind == "WARN"
    assert result.delivery_intent.salience == 1.0


def test_success_prefers_celebration_intent() -> None:
    runtime = CompanionActivityRuntime()
    cognition = CompanionCognition()
    success = evidence(
        "telemetry:success",
        "meaningful_event",
        {"event_id": "boss:defeated", "kind": "success", "description": "Boss defeated"},
        source_kind="telemetry",
        trust_level="system_trusted",
        confidence=1.0,
    )
    before = initial_state()
    activity = runtime.reduce(before, (success,), now=NOW)
    result = cognition.evaluate(
        before=before,
        activity_result=activity,
        propositions=(success,),
        now=NOW,
    )

    assert result.delivery_intent.kind == "CELEBRATE"


def test_open_loop_resolution_creates_state_effect_and_followup_intent() -> None:
    runtime = CompanionActivityRuntime()
    cognition = CompanionCognition()
    open_evidence = evidence(
        "user:loop",
        "open_loop",
        {
            "loop_id": "loop:three-more",
            "kind": "commitment",
            "description": "Give it three more attempts",
            "importance": 0.8,
        },
        source_kind="user",
        trust_level="user_explicit",
        confidence=1.0,
    )
    before = runtime.reduce(initial_state(), (open_evidence,), now=NOW).state
    resolution = evidence(
        "user:resolved",
        "open_loop_status",
        {"loop_id": "loop:three-more", "status": "resolved"},
        source_kind="user",
        trust_level="user_explicit",
        confidence=1.0,
        seconds=1,
    )
    activity = runtime.reduce(before, (resolution,), now=NOW + timedelta(seconds=1))
    result = cognition.evaluate(
        before=before,
        activity_result=activity,
        propositions=(resolution,),
        now=NOW + timedelta(seconds=1),
    )

    assert result.effects.open_loop_updates[0].loop_id == "loop:three-more"
    assert result.effects.open_loop_updates[0].status == "resolved"
    assert result.delivery_intent.kind == "ASK"
