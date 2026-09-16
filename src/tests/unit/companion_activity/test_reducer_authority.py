from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.companion_activity.authority import activity_field_policy
from app.companion_activity.contracts import EvidenceProposition
from app.companion_activity.reducer import ActivityReducer
from app.companion_activity.state import empty_activity_state

NOW = datetime(2026, 9, 14, 23, 0, tzinfo=timezone.utc)


def evidence(
    proposition_id: str,
    predicate: str,
    value,
    *,
    source_kind: str,
    trust_level: str,
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


def state():
    return empty_activity_state(
        activity_id="activity:1",
        session_id="chat:1",
        character_id="sofia",
        started_at=NOW,
    )


def test_user_explicit_objective_beats_visual_inference() -> None:
    reducer = ActivityReducer()
    visual = evidence(
        "screen:1",
        "current_objective",
        "beat Malenia",
        source_kind="external",
        trust_level="external_untrusted",
        confidence=0.99,
    )
    user = evidence(
        "user:1",
        "current_objective",
        "farm runes",
        source_kind="user",
        trust_level="user_explicit",
        confidence=1.0,
        seconds=1,
    )

    result = reducer.reduce(state(), (visual, user), now=NOW + timedelta(seconds=2))
    field = result.state.field("current_objective")

    assert field is not None
    assert field.value == "farm runes"
    assert field.authority_source == "user_explicit"
    assert field.proposition_ids == ("user:1",)


def test_process_integration_beats_user_guess_for_application_fact() -> None:
    reducer = ActivityReducer()
    user_guess = evidence(
        "user:guess",
        "application_or_game",
        "Discord",
        source_kind="user",
        trust_level="user_explicit",
        confidence=1.0,
    )
    process = evidence(
        "process:1",
        "application_or_game",
        "Elden Ring",
        source_kind="system",
        trust_level="system_trusted",
        confidence=0.9,
        seconds=1,
    )

    result = reducer.reduce(state(), (user_guess, process), now=NOW + timedelta(seconds=2))
    field = result.state.field("application_or_game")

    assert field is not None
    assert field.value == "Elden Ring"
    assert field.authority_source == "trusted_process_integration"


def test_runtime_only_field_rejects_perception() -> None:
    reducer = ActivityReducer()
    visual = evidence(
        "screen:voice",
        "voice_call_connected",
        True,
        source_kind="external",
        trust_level="external_untrusted",
        confidence=1.0,
    )
    runtime = evidence(
        "runtime:voice",
        "voice_call_connected",
        False,
        source_kind="runtime",
        trust_level="system_trusted",
        confidence=1.0,
    )

    result = reducer.reduce(state(), (visual, runtime), now=NOW + timedelta(seconds=1))

    assert result.state.field("voice_call_connected").value is False
    assert "screen:voice" in result.ignored_proposition_ids


def test_deterministic_telemetry_wins_attempt_count_and_count_never_decreases() -> None:
    reducer = ActivityReducer()
    perceived = evidence(
        "screen:attempts",
        "attempt_count",
        8,
        source_kind="external",
        trust_level="external_untrusted",
        confidence=0.99,
    )
    telemetry = evidence(
        "telemetry:attempts",
        "attempt_count",
        7,
        source_kind="telemetry",
        trust_level="system_trusted",
        confidence=1.0,
    )
    first = reducer.reduce(state(), (perceived, telemetry), now=NOW + timedelta(seconds=1))
    assert first.state.field("attempt_count").value == 7
    assert first.state.field("attempt_count").authority_source == "deterministic_telemetry"

    stale_lower = evidence(
        "telemetry:lower",
        "attempt_count",
        6,
        source_kind="telemetry",
        trust_level="system_trusted",
        confidence=1.0,
        seconds=2,
    )
    second = reducer.reduce(
        first.state,
        (stale_lower,),
        now=NOW + timedelta(seconds=3),
    )
    assert second.state.field("attempt_count").value == 7
    assert "telemetry:lower" in second.ignored_proposition_ids


def test_repeated_perception_has_more_field_authority_than_single_perception() -> None:
    reducer = ActivityReducer()
    repeated_a = evidence(
        "screen:a",
        "current_phase",
        "phase two",
        source_kind="external",
        trust_level="external_untrusted",
        confidence=0.8,
    )
    repeated_b = evidence(
        "screen:b",
        "current_phase",
        "phase two",
        source_kind="external",
        trust_level="external_untrusted",
        confidence=0.81,
        seconds=1,
    )
    single = evidence(
        "screen:c",
        "current_phase",
        "phase three",
        source_kind="external",
        trust_level="external_untrusted",
        confidence=0.99,
        seconds=2,
    )

    result = reducer.reduce(
        state(),
        (repeated_a, repeated_b, single),
        now=NOW + timedelta(seconds=3),
    )
    field = result.state.field("current_phase")

    assert field.value == "phase two"
    assert field.authority_source == "repeated_perception"
    assert field.proposition_ids == ("screen:a", "screen:b")


def test_authority_policy_is_field_specific_not_global() -> None:
    objective = activity_field_policy("current_objective")
    app = activity_field_policy("application_or_game")
    assert objective is not None and app is not None
    assert objective.authority_rank("user_explicit") < objective.authority_rank(
        "repeated_perception"
    )
    assert app.authority_rank("trusted_process_integration") < app.authority_rank(
        "user_explicit"
    )
