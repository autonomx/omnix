from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.companion_activity.contracts import EvidenceProposition
from app.companion_activity.runtime import CompanionActivityRuntime
from app.companion_activity.state import empty_activity_state

NOW = datetime(2026, 9, 14, 23, 30, tzinfo=timezone.utc)


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
        observed_at=NOW + timedelta(seconds=seconds),
    )


def initial_state():
    return empty_activity_state(
        activity_id="activity:1",
        session_id="chat:1",
        character_id="sofia",
        started_at=NOW,
    )


def test_single_perceptual_frame_does_not_flip_objective_but_repetition_does() -> None:
    runtime = CompanionActivityRuntime()
    first = runtime.reduce(
        initial_state(),
        (
            evidence(
                "screen:1",
                "current_objective",
                "beat Malenia",
                seconds=1,
            ),
        ),
        now=NOW + timedelta(seconds=1),
    )
    assert first.state.field("current_objective") is None
    assert first.state.pending_transitions[0].confirmation_count == 1

    second = runtime.reduce(
        first.state,
        (
            evidence(
                "screen:2",
                "current_objective",
                "beat Malenia",
                seconds=2,
            ),
        ),
        now=NOW + timedelta(seconds=2),
    )
    objective = second.state.field("current_objective")
    assert objective is not None
    assert objective.value == "beat Malenia"
    assert objective.authority_source == "repeated_perception"
    assert objective.proposition_ids == ("screen:1", "screen:2")


def test_explicit_user_correction_bypasses_hysteresis_immediately() -> None:
    runtime = CompanionActivityRuntime()
    established = runtime.reduce(
        initial_state(),
        (
            evidence("screen:1", "current_objective", "beat Malenia"),
            evidence("screen:2", "current_objective", "beat Malenia", seconds=1),
        ),
        now=NOW + timedelta(seconds=1),
    ).state
    corrected = runtime.reduce(
        established,
        (
            evidence(
                "user:correction",
                "current_objective",
                "farm runes",
                source_kind="user",
                trust_level="user_explicit",
                confidence=1.0,
                seconds=2,
            ),
        ),
        now=NOW + timedelta(seconds=2),
    )

    objective = corrected.state.field("current_objective")
    assert objective.value == "farm runes"
    assert objective.authority_source == "user_explicit"
    assert objective.last_transition_reason == "higher_field_authority:user_explicit"


def test_strategy_requires_three_perceptual_confirmations() -> None:
    runtime = CompanionActivityRuntime()
    state = initial_state()
    for index in range(1, 3):
        result = runtime.reduce(
            state,
            (
                evidence(
                    f"screen:{index}",
                    "strategy",
                    "bleed build",
                    seconds=index,
                ),
            ),
            now=NOW + timedelta(seconds=index),
        )
        state = result.state
        assert state.field("strategy") is None

    third = runtime.reduce(
        state,
        (evidence("screen:3", "strategy", "bleed build", seconds=3),),
        now=NOW + timedelta(seconds=3),
    )
    assert third.state.field("strategy").value == "bleed build"
    assert third.state.field("strategy").authority_source == "repeated_perception"


def test_short_lived_runtime_fact_expires_without_erasing_persistent_objective() -> None:
    runtime = CompanionActivityRuntime()
    seeded = runtime.reduce(
        initial_state(),
        (
            evidence(
                "runtime:app",
                "foreground_application",
                "Elden Ring",
                source_kind="runtime",
                trust_level="system_trusted",
            ),
            evidence(
                "user:objective",
                "current_objective",
                "beat Malenia",
                source_kind="user",
                trust_level="user_explicit",
                confidence=1.0,
            ),
        ),
        now=NOW,
    ).state

    expired = runtime.reduce(
        seeded,
        (),
        now=NOW + timedelta(seconds=31),
    )
    assert expired.state.field("foreground_application") is None
    assert expired.state.field("current_objective").value == "beat Malenia"
    assert any(change.reason == "field_stale_expired" for change in expired.changes)


def test_open_loop_has_identity_and_authorized_resolution_lifecycle() -> None:
    runtime = CompanionActivityRuntime()
    opened = runtime.reduce(
        initial_state(),
        (
            evidence(
                "user:loop",
                "open_loop",
                {
                    "loop_id": "loop:three-more",
                    "kind": "commitment",
                    "description": "Give the boss three more attempts",
                    "importance": 0.8,
                },
                source_kind="user",
                trust_level="user_explicit",
                confidence=1.0,
            ),
        ),
        now=NOW,
    ).state
    loop = opened.open_loop("loop:three-more")
    assert loop is not None
    assert loop.status == "open"
    assert loop.activity_id == "activity:1"

    weak_resolution = runtime.reduce(
        opened,
        (
            evidence(
                "screen:resolve",
                "open_loop_status",
                {"loop_id": "loop:three-more", "status": "resolved"},
                confidence=0.99,
                seconds=1,
            ),
        ),
        now=NOW + timedelta(seconds=1),
    ).state
    assert weak_resolution.open_loop("loop:three-more").status == "open"

    resolved = runtime.reduce(
        weak_resolution,
        (
            evidence(
                "user:resolve",
                "open_loop_status",
                {"loop_id": "loop:three-more", "status": "resolved"},
                source_kind="user",
                trust_level="user_explicit",
                confidence=1.0,
                seconds=2,
            ),
        ),
        now=NOW + timedelta(seconds=2),
    ).state
    loop = resolved.open_loop("loop:three-more")
    assert loop.status == "resolved"
    assert loop.resolution_evidence == ("user:resolve",)


def test_progress_markers_events_and_blockers_are_bounded_structured_state() -> None:
    runtime = CompanionActivityRuntime()
    result = runtime.reduce(
        initial_state(),
        (
            evidence(
                "telemetry:progress",
                "progress_marker",
                {"marker_id": "boss:phase2", "description": "Reached phase two"},
                source_kind="telemetry",
                trust_level="system_trusted",
                confidence=1.0,
            ),
            evidence(
                "screen:event",
                "meaningful_event",
                {"event_id": "death:7", "kind": "failure", "description": "Attempt ended"},
                confidence=0.9,
            ),
            evidence(
                "user:blocker",
                "blocker",
                "running out of healing",
                source_kind="user",
                trust_level="user_explicit",
                confidence=1.0,
            ),
        ),
        now=NOW,
    )

    assert result.state.progress_markers[0].marker_id == "boss:phase2"
    assert result.state.recent_meaningful_events[0].event_id == "death:7"
    assert result.state.blockers == ("running out of healing",)
