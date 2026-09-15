"""Deterministic replay evaluation and release gating for the Companion Activity Runtime."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from .cognition import CompanionCognition, DeliveryIntentKind
from .contracts import EvidenceProposition, FrozenContract
from .delivery_quality import DeliveryQualityMetricsSnapshot
from .runtime import CompanionActivityRuntime
from .state import CompanionActivityState

ReplayViolationCode = Literal[
    "field_mismatch",
    "unexpected_field",
    "authority_mismatch",
    "open_loop_status_mismatch",
    "delivery_intent_mismatch",
]
ReleaseGateStatus = Literal["pass", "fail", "insufficient"]


class ReplayExpectation(FrozenContract):
    fields: dict[str, Any] = Field(default_factory=dict)
    absent_fields: tuple[str, ...] = ()
    authorities: dict[str, str] = Field(default_factory=dict)
    open_loop_statuses: dict[str, str] = Field(default_factory=dict)
    delivery_intent: DeliveryIntentKind | None = None


class ReplayStep(FrozenContract):
    at: datetime
    propositions: tuple[EvidenceProposition, ...] = ()
    expectation: ReplayExpectation = Field(default_factory=ReplayExpectation)


class ReplayScenario(FrozenContract):
    scenario_id: str = Field(min_length=1, max_length=160)
    initial_state: CompanionActivityState
    steps: tuple[ReplayStep, ...] = Field(min_length=1, max_length=200)


class ReplayViolation(FrozenContract):
    code: ReplayViolationCode
    step_index: int = Field(ge=0)
    field_name: str | None = Field(default=None, max_length=160)
    loop_id: str | None = Field(default=None, max_length=240)


class ReplayScenarioResult(FrozenContract):
    scenario_id: str
    passed: bool
    steps_completed: int = Field(ge=0)
    final_revision: int = Field(ge=0)
    violations: tuple[ReplayViolation, ...] = ()


class CompanionReplayEvaluator:
    """Replay evidence through the same reducer/cognition path used by production."""

    def __init__(
        self,
        *,
        runtime: CompanionActivityRuntime | None = None,
        cognition: CompanionCognition | None = None,
    ) -> None:
        self._runtime = runtime or CompanionActivityRuntime()
        self._cognition = cognition or CompanionCognition()

    def run(self, scenario: ReplayScenario) -> ReplayScenarioResult:
        state = scenario.initial_state
        violations: list[ReplayViolation] = []
        for index, step in enumerate(scenario.steps):
            before = state
            activity = self._runtime.reduce(before, step.propositions, now=step.at)
            cognition = self._cognition.evaluate(
                before=before,
                activity_result=activity,
                propositions=step.propositions,
                now=step.at,
            )
            state = activity.state
            violations.extend(
                _check_expectation(
                    state,
                    cognition.delivery_intent.kind,
                    step.expectation,
                    step_index=index,
                )
            )
        return ReplayScenarioResult(
            scenario_id=scenario.scenario_id,
            passed=not violations,
            steps_completed=len(scenario.steps),
            final_revision=state.revision,
            violations=tuple(violations),
        )

    def run_all(self, scenarios: tuple[ReplayScenario, ...]) -> tuple[ReplayScenarioResult, ...]:
        return tuple(self.run(scenario) for scenario in scenarios)


class CompanionReleaseEvidence(FrozenContract):
    replay_results: tuple[ReplayScenarioResult, ...] = ()
    quality_metrics: DeliveryQualityMetricsSnapshot
    provenance_trust_violations: int = Field(default=0, ge=0)
    sensitivity_downgrade_violations: int = Field(default=0, ge=0)
    authority_boundary_violations: int = Field(default=0, ge=0)
    recovery_failures: int = Field(default=0, ge=0)


class CompanionReleaseGatePolicy(FrozenContract):
    minimum_replay_scenarios: int = Field(default=8, ge=1)
    minimum_behavior_samples: int = Field(default=50, ge=1)
    max_stale_comment_rate: float = Field(default=0.10, ge=0.0, le=1.0)
    max_repeated_comment_rate: float = Field(default=0.10, ge=0.0, le=1.0)
    max_interruption_rate: float = Field(default=0.10, ge=0.0, le=1.0)
    max_ignored_initiative_rate: float = Field(default=0.25, ge=0.0, le=1.0)
    max_false_objective_transition_rate: float = Field(default=0.05, ge=0.0, le=1.0)


class CompanionReleaseGateReport(FrozenContract):
    status: ReleaseGateStatus
    reasons: tuple[str, ...] = ()
    replay_scenarios: int = Field(ge=0)
    replay_failures: int = Field(ge=0)
    behavior_samples: int = Field(ge=0)


class CompanionReleaseGate:
    """Hard-fail authority/recovery defects; require enough behavioral evidence to pass."""

    def evaluate(
        self,
        evidence: CompanionReleaseEvidence,
        *,
        policy: CompanionReleaseGatePolicy | None = None,
    ) -> CompanionReleaseGateReport:
        policy = policy or CompanionReleaseGatePolicy()
        failures = tuple(item for item in evidence.replay_results if not item.passed)
        hard_reasons: list[str] = []
        if evidence.provenance_trust_violations:
            hard_reasons.append("provenance_trust_violation")
        if evidence.sensitivity_downgrade_violations:
            hard_reasons.append("sensitivity_downgrade_violation")
        if evidence.authority_boundary_violations:
            hard_reasons.append("authority_boundary_violation")
        if evidence.recovery_failures:
            hard_reasons.append("recovery_failure")
        if failures:
            hard_reasons.append("replay_scenario_failure")
        if hard_reasons:
            return _gate_report("fail", hard_reasons, evidence, failures)

        insufficient: list[str] = []
        if len(evidence.replay_results) < policy.minimum_replay_scenarios:
            insufficient.append("insufficient_replay_scenarios")
        metrics = evidence.quality_metrics
        if metrics.samples < policy.minimum_behavior_samples:
            insufficient.append("insufficient_behavior_samples")
        if insufficient:
            return _gate_report("insufficient", insufficient, evidence, failures)

        rate_reasons: list[str] = []
        checks = (
            (metrics.stale_comment_rate, policy.max_stale_comment_rate, "stale_comment_rate"),
            (
                metrics.repeated_comment_rate,
                policy.max_repeated_comment_rate,
                "repeated_comment_rate",
            ),
            (metrics.interruption_rate, policy.max_interruption_rate, "interruption_rate"),
            (
                metrics.ignored_initiative_rate,
                policy.max_ignored_initiative_rate,
                "ignored_initiative_rate",
            ),
            (
                metrics.false_objective_transition_rate,
                policy.max_false_objective_transition_rate,
                "false_objective_transition_rate",
            ),
        )
        for actual, maximum, name in checks:
            if actual > maximum:
                rate_reasons.append(f"{name}_exceeded")
        if rate_reasons:
            return _gate_report("fail", rate_reasons, evidence, failures)
        return _gate_report("pass", (), evidence, failures)


def _check_expectation(
    state: CompanionActivityState,
    delivery_kind: DeliveryIntentKind,
    expectation: ReplayExpectation,
    *,
    step_index: int,
) -> list[ReplayViolation]:
    violations: list[ReplayViolation] = []
    for field_name, expected in expectation.fields.items():
        field = state.field(field_name)
        if field is None or field.value != expected:
            violations.append(
                ReplayViolation(
                    code="field_mismatch",
                    step_index=step_index,
                    field_name=field_name,
                )
            )
    for field_name in expectation.absent_fields:
        if state.field(field_name) is not None:
            violations.append(
                ReplayViolation(
                    code="unexpected_field",
                    step_index=step_index,
                    field_name=field_name,
                )
            )
    for field_name, expected_authority in expectation.authorities.items():
        field = state.field(field_name)
        if field is None or field.authority_source != expected_authority:
            violations.append(
                ReplayViolation(
                    code="authority_mismatch",
                    step_index=step_index,
                    field_name=field_name,
                )
            )
    for loop_id, expected_status in expectation.open_loop_statuses.items():
        loop = state.open_loop(loop_id)
        if loop is None or loop.status != expected_status:
            violations.append(
                ReplayViolation(
                    code="open_loop_status_mismatch",
                    step_index=step_index,
                    loop_id=loop_id,
                )
            )
    if expectation.delivery_intent is not None and delivery_kind != expectation.delivery_intent:
        violations.append(
            ReplayViolation(
                code="delivery_intent_mismatch",
                step_index=step_index,
            )
        )
    return violations


def _gate_report(
    status: ReleaseGateStatus,
    reasons: list[str] | tuple[str, ...],
    evidence: CompanionReleaseEvidence,
    failures: tuple[ReplayScenarioResult, ...],
) -> CompanionReleaseGateReport:
    return CompanionReleaseGateReport(
        status=status,
        reasons=tuple(dict.fromkeys(reasons)),
        replay_scenarios=len(evidence.replay_results),
        replay_failures=len(failures),
        behavior_samples=evidence.quality_metrics.samples,
    )


__all__ = [
    "CompanionReleaseEvidence",
    "CompanionReleaseGate",
    "CompanionReleaseGatePolicy",
    "CompanionReleaseGateReport",
    "CompanionReplayEvaluator",
    "ReplayExpectation",
    "ReplayScenario",
    "ReplayScenarioResult",
    "ReplayStep",
    "ReplayViolation",
]
