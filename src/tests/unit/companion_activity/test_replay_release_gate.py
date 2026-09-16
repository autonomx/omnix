from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.companion_activity.contracts import EvidenceProposition
from app.companion_activity.delivery_quality import (
    CompanionDeliveryQualityMetrics,
    DeliveryQualityOutcome,
)
from app.companion_activity.evaluation import (
    CompanionReleaseEvidence,
    CompanionReleaseGate,
    CompanionReleaseGatePolicy,
    CompanionReplayEvaluator,
    ReplayExpectation,
    ReplayScenario,
    ReplayStep,
)
from app.companion_activity.state import empty_activity_state

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def p(
    proposition_id: str,
    predicate: str,
    value,
    *,
    source_kind: str = "external",
    trust_level: str = "external_untrusted",
    confidence: float = 0.9,
    seconds: int = 0,
    sensitivity: str = "normal",
    generation: str | None = None,
) -> EvidenceProposition:
    return EvidenceProposition(
        proposition_id=proposition_id,
        subject="activity:acceptance",
        predicate=predicate,
        value=value,
        source_kind=source_kind,
        trust_level=trust_level,
        confidence=confidence,
        sensitivity=sensitivity,
        observed_at=NOW + timedelta(seconds=seconds),
        generation=generation,
    )


def base_state(scenario_id: str):
    return empty_activity_state(
        activity_id=f"activity:{scenario_id}",
        session_id=f"chat:{scenario_id}",
        started_at=NOW,
        generation="generation:1",
    )


def acceptance_scenarios() -> tuple[ReplayScenario, ...]:
    return (
        ReplayScenario(
            scenario_id="visual-objective-hysteresis",
            initial_state=base_state("visual-objective-hysteresis"),
            coverage_tags=("authority", "hysteresis", "cognition"),
            steps=(
                ReplayStep(
                    at=NOW,
                    propositions=(p("screen:o1", "current_objective", "beat Malenia"),),
                    expectation=ReplayExpectation(
                        absent_fields=("current_objective",),
                        delivery_intent="IGNORE",
                    ),
                ),
                ReplayStep(
                    at=NOW + timedelta(seconds=1),
                    propositions=(
                        p("screen:o2", "current_objective", "beat Malenia", seconds=1),
                    ),
                    expectation=ReplayExpectation(
                        fields={"current_objective": "beat Malenia"},
                        authorities={"current_objective": "repeated_perception"},
                        delivery_intent="REACT",
                    ),
                ),
            ),
        ),
        ReplayScenario(
            scenario_id="explicit-user-correction",
            initial_state=base_state("explicit-user-correction"),
            coverage_tags=("authority",),
            steps=(
                ReplayStep(
                    at=NOW,
                    propositions=(
                        p(
                            "telemetry:objective",
                            "current_objective",
                            "beat Malenia",
                            source_kind="telemetry",
                            trust_level="system_trusted",
                            confidence=1.0,
                        ),
                    ),
                    expectation=ReplayExpectation(
                        fields={"current_objective": "beat Malenia"},
                        authorities={"current_objective": "deterministic_telemetry"},
                    ),
                ),
                ReplayStep(
                    at=NOW + timedelta(seconds=2),
                    propositions=(
                        p(
                            "user:objective",
                            "current_objective",
                            "farm runes",
                            source_kind="user",
                            trust_level="user_explicit",
                            confidence=1.0,
                            seconds=2,
                        ),
                    ),
                    expectation=ReplayExpectation(
                        fields={"current_objective": "farm runes"},
                        authorities={"current_objective": "user_explicit"},
                        delivery_intent="IGNORE",
                    ),
                ),
            ),
        ),
        ReplayScenario(
            scenario_id="alt-tab-retains-activity",
            initial_state=base_state("alt-tab-retains-activity"),
            coverage_tags=("authority",),
            steps=(
                ReplayStep(
                    at=NOW,
                    propositions=(
                        p(
                            "process:fg:1",
                            "foreground_application",
                            "eldenring.exe",
                            source_kind="system",
                            trust_level="system_trusted",
                            confidence=1.0,
                        ),
                        p(
                            "process:activity:1",
                            "application_or_game",
                            "Elden Ring",
                            source_kind="system",
                            trust_level="system_trusted",
                            confidence=1.0,
                        ),
                    ),
                    expectation=ReplayExpectation(
                        fields={
                            "foreground_application": "eldenring.exe",
                            "application_or_game": "Elden Ring",
                        },
                    ),
                ),
                ReplayStep(
                    at=NOW + timedelta(seconds=2),
                    propositions=(
                        p(
                            "process:fg:2",
                            "foreground_application",
                            "discord.exe",
                            source_kind="runtime",
                            trust_level="system_trusted",
                            confidence=1.0,
                            seconds=2,
                        ),
                    ),
                    expectation=ReplayExpectation(
                        fields={
                            "foreground_application": "discord.exe",
                            "application_or_game": "Elden Ring",
                        },
                    ),
                ),
            ),
        ),
        ReplayScenario(
            scenario_id="attempt-count-monotonic",
            initial_state=base_state("attempt-count-monotonic"),
            coverage_tags=("authority", "monotonic_count"),
            steps=(
                ReplayStep(
                    at=NOW,
                    propositions=(
                        p(
                            "telemetry:a7",
                            "attempt_count",
                            7,
                            source_kind="telemetry",
                            trust_level="system_trusted",
                            confidence=1.0,
                        ),
                    ),
                    expectation=ReplayExpectation(
                        fields={"attempt_count": 7},
                        authorities={"attempt_count": "deterministic_telemetry"},
                    ),
                ),
                ReplayStep(
                    at=NOW + timedelta(seconds=1),
                    propositions=(
                        p(
                            "telemetry:a6",
                            "attempt_count",
                            6,
                            source_kind="telemetry",
                            trust_level="system_trusted",
                            confidence=1.0,
                            seconds=1,
                        ),
                    ),
                    expectation=ReplayExpectation(fields={"attempt_count": 7}),
                ),
            ),
        ),
        ReplayScenario(
            scenario_id="strategy-jitter-hysteresis",
            initial_state=base_state("strategy-jitter-hysteresis"),
            coverage_tags=("hysteresis",),
            steps=(
                ReplayStep(
                    at=NOW,
                    propositions=(p("screen:s1", "strategy", "bleed build"),),
                    expectation=ReplayExpectation(absent_fields=("strategy",)),
                ),
                ReplayStep(
                    at=NOW + timedelta(seconds=1),
                    propositions=(p("screen:s2", "strategy", "bleed build", seconds=1),),
                    expectation=ReplayExpectation(absent_fields=("strategy",)),
                ),
                ReplayStep(
                    at=NOW + timedelta(seconds=2),
                    propositions=(p("screen:s3", "strategy", "bleed build", seconds=2),),
                    expectation=ReplayExpectation(fields={"strategy": "bleed build"}),
                ),
            ),
        ),
        ReplayScenario(
            scenario_id="open-loop-lifecycle",
            initial_state=base_state("open-loop-lifecycle"),
            coverage_tags=("authority", "open_loop", "cognition"),
            steps=(
                ReplayStep(
                    at=NOW,
                    propositions=(
                        p(
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
                        ),
                    ),
                    expectation=ReplayExpectation(
                        open_loop_statuses={"loop:three-more": "open"},
                    ),
                ),
                ReplayStep(
                    at=NOW + timedelta(seconds=3),
                    propositions=(
                        p(
                            "user:loop:resolved",
                            "open_loop_status",
                            {"loop_id": "loop:three-more", "status": "resolved"},
                            source_kind="user",
                            trust_level="user_explicit",
                            confidence=1.0,
                            seconds=3,
                        ),
                    ),
                    expectation=ReplayExpectation(
                        open_loop_statuses={"loop:three-more": "resolved"},
                        delivery_intent="ASK",
                    ),
                ),
            ),
        ),
        ReplayScenario(
            scenario_id="success-celebration",
            initial_state=base_state("success-celebration"),
            coverage_tags=("cognition",),
            steps=(
                ReplayStep(
                    at=NOW,
                    propositions=(
                        p(
                            "telemetry:success",
                            "meaningful_event",
                            {
                                "event_id": "boss:defeated",
                                "kind": "success",
                                "description": "Boss defeated",
                            },
                            source_kind="telemetry",
                            trust_level="system_trusted",
                            confidence=1.0,
                        ),
                    ),
                    expectation=ReplayExpectation(delivery_intent="CELEBRATE"),
                ),
            ),
        ),
        ReplayScenario(
            scenario_id="destructive-warning",
            initial_state=base_state("destructive-warning"),
            coverage_tags=("cognition", "warning"),
            steps=(
                ReplayStep(
                    at=NOW,
                    propositions=(
                        p(
                            "runtime:danger",
                            "destructive_risk",
                            "unsaved work may be deleted",
                            source_kind="runtime",
                            trust_level="system_trusted",
                            confidence=0.98,
                        ),
                    ),
                    expectation=ReplayExpectation(delivery_intent="WARN"),
                ),
            ),
        ),
        ReplayScenario(
            scenario_id="blocker-advice",
            initial_state=base_state("blocker-advice"),
            coverage_tags=("cognition",),
            steps=(
                ReplayStep(
                    at=NOW,
                    propositions=(
                        p(
                            "screen:blocker",
                            "blocker",
                            "Build fails at typecheck",
                            confidence=0.9,
                            sensitivity="sensitive",
                        ),
                    ),
                    expectation=ReplayExpectation(delivery_intent="ADVISE"),
                ),
            ),
        ),
        ReplayScenario(
            scenario_id="stale-generation-warning-suppressed",
            initial_state=base_state("stale-generation-warning-suppressed"),
            coverage_tags=("authority", "generation", "warning"),
            steps=(
                ReplayStep(
                    at=NOW,
                    propositions=(
                        p(
                            "old:danger",
                            "destructive_risk",
                            "stale warning",
                            source_kind="runtime",
                            trust_level="system_trusted",
                            confidence=1.0,
                            generation="generation:0",
                        ),
                    ),
                    expectation=ReplayExpectation(delivery_intent="IGNORE"),
                ),
            ),
        ),
    )


def clean_metrics(samples: int = 50):
    metrics = CompanionDeliveryQualityMetrics()
    for _ in range(samples):
        metrics.record(DeliveryQualityOutcome(delivered=True))
    return metrics.snapshot()


def complete_release_evidence(*, metrics=None) -> CompanionReleaseEvidence:
    return CompanionReleaseEvidence(
        replay_results=CompanionReplayEvaluator().run_all(acceptance_scenarios()),
        quality_metrics=metrics or clean_metrics(),
        provenance_trust_checks=1,
        sensitivity_policy_checks=1,
        authority_boundary_checks=1,
        recovery_checks=1,
    )


def test_acceptance_replay_matrix_covers_authority_hysteresis_progress_and_cognition() -> None:
    results = CompanionReplayEvaluator().run_all(acceptance_scenarios())

    assert len(results) >= 8
    assert all(result.passed for result in results), [
        (result.scenario_id, result.violations) for result in results if not result.passed
    ]
    coverage = {tag for result in results for tag in result.coverage_tags}
    assert {
        "authority",
        "hysteresis",
        "monotonic_count",
        "open_loop",
        "cognition",
        "warning",
        "generation",
    } <= coverage


def test_replay_failures_are_content_free_codes_not_observed_values() -> None:
    scenario = ReplayScenario(
        scenario_id="intentional-mismatch",
        initial_state=base_state("intentional-mismatch"),
        steps=(
            ReplayStep(
                at=NOW,
                propositions=(
                    p(
                        "runtime:voice",
                        "voice_call_connected",
                        True,
                        source_kind="runtime",
                        trust_level="system_trusted",
                        confidence=1.0,
                    ),
                ),
                expectation=ReplayExpectation(fields={"voice_call_connected": False}),
            ),
        ),
    )
    result = CompanionReplayEvaluator().run(scenario)

    assert result.passed is False
    assert result.violations[0].code == "field_mismatch"
    assert result.violations[0].field_name == "voice_call_connected"
    serialized = result.model_dump_json()
    assert "True" not in serialized
    assert "False" not in serialized


def test_release_gate_passes_only_with_clean_authority_and_enough_behavior_evidence() -> None:
    report = CompanionReleaseGate().evaluate(complete_release_evidence())

    assert report.status == "pass"
    assert report.replay_failures == 0
    assert report.missing_replay_coverage == ()
    assert report.behavior_samples == 50


def test_release_gate_is_insufficient_before_evidence_floor() -> None:
    results = CompanionReplayEvaluator().run_all(acceptance_scenarios()[:4])
    evidence = CompanionReleaseEvidence(
        replay_results=results,
        quality_metrics=clean_metrics(samples=10),
    )

    report = CompanionReleaseGate().evaluate(evidence)

    assert report.status == "insufficient"
    assert "insufficient_replay_scenarios" in report.reasons
    assert "insufficient_replay_coverage" in report.reasons
    assert "insufficient_behavior_samples" in report.reasons
    assert "insufficient_recovery_checks" in report.reasons


def test_release_gate_rejects_arbitrary_scenario_count_without_required_coverage() -> None:
    scenarios = acceptance_scenarios()[:-1]
    results = CompanionReplayEvaluator().run_all(scenarios)
    evidence = CompanionReleaseEvidence(
        replay_results=results,
        quality_metrics=clean_metrics(),
        provenance_trust_checks=1,
        sensitivity_policy_checks=1,
        authority_boundary_checks=1,
        recovery_checks=1,
    )

    report = CompanionReleaseGate().evaluate(evidence)

    assert report.status == "insufficient"
    assert "insufficient_replay_coverage" in report.reasons
    assert "generation" in report.missing_replay_coverage


def test_release_gate_hard_fails_authority_recovery_or_replay_violations() -> None:
    evidence = complete_release_evidence().model_copy(
        update={
            "provenance_trust_violations": 1,
            "authority_boundary_violations": 1,
            "recovery_failures": 1,
        }
    )

    report = CompanionReleaseGate().evaluate(evidence)

    assert report.status == "fail"
    assert "provenance_trust_violation" in report.reasons
    assert "authority_boundary_violation" in report.reasons
    assert "recovery_failure" in report.reasons


def test_release_gate_fails_behavior_rates_after_sample_floor() -> None:
    metrics = CompanionDeliveryQualityMetrics()
    for index in range(50):
        metrics.record(
            DeliveryQualityOutcome(
                delivered=True,
                stale_suppressed=index < 10,
                repeated_suppressed=index < 10,
                interrupted=index < 10,
                false_objective_transition=index < 5,
            )
        )
    evidence = complete_release_evidence(metrics=metrics.snapshot())

    report = CompanionReleaseGate().evaluate(
        evidence,
        policy=CompanionReleaseGatePolicy(minimum_behavior_samples=50),
    )

    assert report.status == "fail"
    assert "stale_comment_rate_exceeded" in report.reasons
    assert "repeated_comment_rate_exceeded" in report.reasons
    assert "interruption_rate_exceeded" in report.reasons
    assert "false_objective_transition_rate_exceeded" in report.reasons
