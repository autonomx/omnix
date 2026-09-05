from __future__ import annotations

import json

from app.agent_runtime.quality_evaluation import (
    CodingQualitySample,
    SeededQualityProbe,
    aggregate_quality_samples,
    compare_quality_baseline,
    evaluate_rollout_policy,
    write_evaluation_report,
)


def _sample(
    scenario_id: str,
    variant: str,
    *,
    completed: bool = True,
    requirements_satisfied: int = 4,
    final_state_validated: bool = True,
    stale_validation_accepted: bool = False,
    stale_review_accepted: bool = False,
    injected_defect: bool = True,
    reviewer_caught_defect: bool | None = None,
    repair_attempts: int = 1,
    repair_succeeded: bool | None = None,
    output_tokens: int = 1000,
    tool_calls: int = 20,
    wall_time_seconds: float = 30.0,
) -> CodingQualitySample:
    candidate = variant == "candidate"
    return CodingQualitySample(
        scenario_id=scenario_id,
        variant=variant,
        quality_policy="strict" if candidate else "off",
        completed=completed,
        requirements_total=4,
        requirements_satisfied=requirements_satisfied,
        final_state_validated=final_state_validated,
        stale_validation_accepted=stale_validation_accepted,
        stale_review_accepted=stale_review_accepted,
        reviewer_required=candidate,
        reviewer_approved=True if candidate else None,
        injected_defect=injected_defect,
        reviewer_caught_defect=(
            reviewer_caught_defect if candidate else None
        ),
        repair_attempts=repair_attempts if candidate else 0,
        repair_succeeded=repair_succeeded if candidate else None,
        output_tokens=output_tokens,
        tool_calls=tool_calls,
        wall_time_seconds=wall_time_seconds,
    )


def test_aggregate_measures_quality_and_efficiency() -> None:
    rows = [
        _sample("a", "candidate", reviewer_caught_defect=True, repair_succeeded=True),
        _sample(
            "b",
            "candidate",
            requirements_satisfied=3,
            reviewer_caught_defect=False,
            repair_succeeded=False,
            output_tokens=1400,
            tool_calls=30,
            wall_time_seconds=50,
        ),
    ]
    result = aggregate_quality_samples(rows, variant="candidate")
    assert result.scenario_count == 2
    assert result.completion_rate == 1.0
    assert result.requirement_coverage_rate == 0.875
    assert result.reviewer_catch_rate == 0.5
    assert result.repair_success_rate == 0.5
    assert result.average_output_tokens == 1200
    assert result.average_tool_calls == 25
    assert result.average_wall_time_seconds == 40


def test_strict_rollout_accepts_measurably_better_candidate() -> None:
    baseline = [
        _sample(
            "a",
            "baseline",
            requirements_satisfied=3,
            final_state_validated=False,
            output_tokens=1000,
            wall_time_seconds=30,
        ),
        _sample(
            "b",
            "baseline",
            requirements_satisfied=3,
            final_state_validated=False,
            output_tokens=1000,
            wall_time_seconds=30,
        ),
    ]
    candidate = [
        _sample(
            "a",
            "candidate",
            reviewer_caught_defect=True,
            repair_succeeded=True,
            output_tokens=1800,
            wall_time_seconds=55,
        ),
        _sample(
            "b",
            "candidate",
            reviewer_caught_defect=True,
            repair_succeeded=True,
            output_tokens=1800,
            wall_time_seconds=55,
        ),
    ]
    comparison = compare_quality_baseline(baseline, candidate)
    decision = evaluate_rollout_policy(comparison, policy="strict")
    assert comparison.requirement_coverage_delta > 0
    assert comparison.final_state_validation_delta > 0
    assert decision.allowed
    assert decision.reasons == []


def test_strict_rollout_fails_closed_on_stale_validation_acceptance() -> None:
    baseline = [_sample("a", "baseline", injected_defect=False)]
    candidate = [
        _sample(
            "a",
            "candidate",
            stale_validation_accepted=True,
            reviewer_caught_defect=True,
            repair_succeeded=True,
        )
    ]
    decision = evaluate_rollout_policy(
        compare_quality_baseline(baseline, candidate),
        policy="strict",
    )
    assert not decision.allowed
    assert "stale_quality_evidence_was_accepted" in decision.reasons


def test_strict_rollout_requires_review_and_repair_measurement() -> None:
    baseline = [_sample("a", "baseline", injected_defect=False)]
    candidate = [
        _sample(
            "a",
            "candidate",
            injected_defect=False,
            reviewer_caught_defect=None,
            repair_attempts=0,
            repair_succeeded=None,
        )
    ]
    decision = evaluate_rollout_policy(
        compare_quality_baseline(baseline, candidate),
        policy="strict",
    )
    assert not decision.allowed
    assert "reviewer_catch_rate_unmeasured" in decision.reasons
    assert "repair_success_rate_unmeasured" in decision.reasons


def test_rollout_rejects_mismatched_scenario_corpus() -> None:
    baseline = [_sample("a", "baseline")]
    candidate = [
        _sample("b", "candidate", reviewer_caught_defect=True, repair_succeeded=True)
    ]
    comparison = compare_quality_baseline(baseline, candidate)
    decision = evaluate_rollout_policy(comparison, policy="standard")
    assert not decision.allowed
    assert comparison.baseline_only_scenarios == ["a"]
    assert comparison.candidate_only_scenarios == ["b"]
    assert "scenario_corpus_mismatch" in decision.reasons


def test_evaluation_report_is_machine_readable(tmp_path) -> None:
    baseline = [_sample("a", "baseline", injected_defect=False)]
    candidate = [
        _sample(
            "a",
            "candidate",
            reviewer_caught_defect=True,
            repair_succeeded=True,
        )
    ]
    comparison = compare_quality_baseline(baseline, candidate)
    decision = evaluate_rollout_policy(comparison, policy="standard")
    path = write_evaluation_report(tmp_path / "quality.json", comparison, decision)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["comparison"]["matched_scenarios"] == ["a"]
    assert payload["rollout"]["policy"] == "standard"


def test_strict_rollout_uses_seeded_ground_truth_probe_metrics() -> None:
    baseline = [_sample("a", "baseline", injected_defect=False)]
    candidate = [_sample("a", "candidate", injected_defect=False, reviewer_caught_defect=None, repair_attempts=0, repair_succeeded=None)]
    probes = [SeededQualityProbe(probe_id="seeded", defect_id="known-defect", reviewer_caught_defect=True, repair_succeeded=True)]
    comparison = compare_quality_baseline(baseline, candidate, seeded_probes=probes)
    decision = evaluate_rollout_policy(comparison, policy="strict")
    assert comparison.seeded_reviewer_catch_rate == 1.0
    assert comparison.seeded_repair_success_rate == 1.0
    assert "reviewer_catch_rate_unmeasured" not in decision.reasons
    assert "repair_success_rate_unmeasured" not in decision.reasons
