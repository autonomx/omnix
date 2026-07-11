from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .performance import evaluate_latency_benchmark


@dataclass(frozen=True)
class ResponseReleaseMetrics:
    scenario_count: int
    allowed_forward_outcome_count: int
    generic_inert_fallback_count: int = 0
    unsupported_hard_state_claim_count: int = 0
    direct_mutation_path_count: int = 0
    hidden_fact_leak_count: int = 0
    player_agency_violation_count: int = 0
    repeated_action_duplication_count: int = 0
    unvalidated_delivery_count: int = 0
    replay_hash_stable: bool = True
    persistent_proposal_peak: int = 0
    persistent_proposal_budget: int = 64
    normal_turn_latency_ms: tuple[float, ...] = ()
    expected_normal_turn_p95_ms: float = 5000.0
    exact_head_checks_passed: bool = False

    @property
    def forward_outcome_rate(self) -> float:
        return _rate(self.allowed_forward_outcome_count, self.scenario_count)

    @property
    def generic_fallback_rate(self) -> float:
        return _rate(self.generic_inert_fallback_count, self.scenario_count)


@dataclass(frozen=True)
class ReleaseGateResult:
    passed: bool
    issues: tuple[str, ...]
    metrics: Mapping[str, Any]


@dataclass(frozen=True)
class CampaignEvidenceRow:
    turn_id: str
    allowed_forward_outcome: bool
    generic_inert_fallback: bool = False
    unsupported_hard_state_claims: tuple[str, ...] = ()
    direct_mutation_paths: tuple[str, ...] = ()
    hidden_fact_leaks: tuple[str, ...] = ()
    agency_violations: tuple[str, ...] = ()
    repeated_action_duplication: bool = False
    unvalidated_delivery: bool = False
    normal_turn_latency_ms: float | None = None


@dataclass
class CampaignEvidenceAccumulator:
    rows: list[CampaignEvidenceRow] = field(default_factory=list)
    replay_hash_stable: bool = True
    persistent_proposal_peak: int = 0
    persistent_proposal_budget: int = 64
    exact_head_checks_passed: bool = False

    def add(self, row: CampaignEvidenceRow) -> None:
        self.rows.append(row)

    def metrics(self, *, p95_budget_ms: float = 5000.0) -> ResponseReleaseMetrics:
        return metrics_from_campaign_rows(
            self.rows,
            replay_hash_stable=self.replay_hash_stable,
            persistent_proposal_peak=self.persistent_proposal_peak,
            persistent_proposal_budget=self.persistent_proposal_budget,
            exact_head_checks_passed=self.exact_head_checks_passed,
            p95_budget_ms=p95_budget_ms,
        )


def evaluate_response_release_gate(
    metrics: ResponseReleaseMetrics,
    *,
    minimum_forward_outcome_rate: float = 0.95,
    maximum_generic_fallback_rate: float = 0.01,
) -> ReleaseGateResult:
    issues: list[str] = []
    if metrics.scenario_count <= 0:
        issues.append("no_release_scenarios")
    if metrics.forward_outcome_rate < minimum_forward_outcome_rate:
        issues.append("forward_outcome_rate_below_threshold")
    if metrics.generic_fallback_rate >= maximum_generic_fallback_rate:
        issues.append("generic_fallback_rate_not_below_threshold")
    zero_count_gates = {
        "unsupported_hard_state_claims": metrics.unsupported_hard_state_claim_count,
        "direct_mutation_paths": metrics.direct_mutation_path_count,
        "hidden_fact_leaks": metrics.hidden_fact_leak_count,
        "player_agency_violations": metrics.player_agency_violation_count,
        "repeated_action_duplication": metrics.repeated_action_duplication_count,
        "unvalidated_delivery": metrics.unvalidated_delivery_count,
    }
    issues.extend(name for name, count in zero_count_gates.items() if count != 0)
    if not metrics.replay_hash_stable:
        issues.append("replay_hash_unstable")
    if metrics.persistent_proposal_peak > metrics.persistent_proposal_budget:
        issues.append("persistent_proposal_growth_unbounded")
    latency = evaluate_latency_benchmark(
        metrics.normal_turn_latency_ms,
        p95_budget_ms=metrics.expected_normal_turn_p95_ms,
    )
    if metrics.normal_turn_latency_ms and not latency.passed:
        issues.append("normal_turn_p95_latency_exceeded")
    if not metrics.exact_head_checks_passed:
        issues.append("exact_head_checks_not_passed")
    payload = {
        "scenario_count": metrics.scenario_count,
        "forward_outcome_rate": metrics.forward_outcome_rate,
        "generic_fallback_rate": metrics.generic_fallback_rate,
        **zero_count_gates,
        "replay_hash_stable": metrics.replay_hash_stable,
        "persistent_proposal_peak": metrics.persistent_proposal_peak,
        "persistent_proposal_budget": metrics.persistent_proposal_budget,
        "latency": {
            "sample_count": latency.sample_count,
            "p50_ms": latency.p50_ms,
            "p95_ms": latency.p95_ms,
            "budget_ms": latency.budget_ms,
            "passed": latency.passed,
        },
        "exact_head_checks_passed": metrics.exact_head_checks_passed,
    }
    return ReleaseGateResult(not issues, tuple(issues), payload)


def metrics_from_campaign_rows(
    rows: Iterable[CampaignEvidenceRow | Mapping[str, Any]],
    *,
    replay_hash_stable: bool,
    persistent_proposal_peak: int,
    persistent_proposal_budget: int,
    exact_head_checks_passed: bool,
    p95_budget_ms: float = 5000.0,
) -> ResponseReleaseMetrics:
    normalized = tuple(
        row if isinstance(row, CampaignEvidenceRow) else _row_from_mapping(row)
        for row in rows
    )
    return ResponseReleaseMetrics(
        scenario_count=len(normalized),
        allowed_forward_outcome_count=sum(row.allowed_forward_outcome for row in normalized),
        generic_inert_fallback_count=sum(row.generic_inert_fallback for row in normalized),
        unsupported_hard_state_claim_count=sum(bool(row.unsupported_hard_state_claims) for row in normalized),
        direct_mutation_path_count=sum(bool(row.direct_mutation_paths) for row in normalized),
        hidden_fact_leak_count=sum(bool(row.hidden_fact_leaks) for row in normalized),
        player_agency_violation_count=sum(bool(row.agency_violations) for row in normalized),
        repeated_action_duplication_count=sum(row.repeated_action_duplication for row in normalized),
        unvalidated_delivery_count=sum(row.unvalidated_delivery for row in normalized),
        replay_hash_stable=replay_hash_stable,
        persistent_proposal_peak=int(persistent_proposal_peak),
        persistent_proposal_budget=int(persistent_proposal_budget),
        normal_turn_latency_ms=tuple(
            float(row.normal_turn_latency_ms)
            for row in normalized
            if row.normal_turn_latency_ms is not None
        ),
        expected_normal_turn_p95_ms=float(p95_budget_ms),
        exact_head_checks_passed=exact_head_checks_passed,
    )


def _row_from_mapping(row: Mapping[str, Any]) -> CampaignEvidenceRow:
    return CampaignEvidenceRow(
        turn_id=str(row.get("turn_id") or ""),
        allowed_forward_outcome=bool(row.get("allowed_forward_outcome")),
        generic_inert_fallback=bool(row.get("generic_inert_fallback")),
        unsupported_hard_state_claims=_strings(row.get("unsupported_hard_state_claims")),
        direct_mutation_paths=_strings(row.get("direct_mutation_paths")),
        hidden_fact_leaks=_strings(row.get("hidden_fact_leaks")),
        agency_violations=_strings(row.get("agency_violations")),
        repeated_action_duplication=bool(row.get("repeated_action_duplication")),
        unvalidated_delivery=bool(row.get("unvalidated_delivery")),
        normal_turn_latency_ms=(
            float(row["normal_turn_latency_ms"])
            if row.get("normal_turn_latency_ms") is not None
            else None
        ),
    )


def _strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    try:
        return tuple(str(item) for item in value if str(item))
    except TypeError:
        return ()


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)
