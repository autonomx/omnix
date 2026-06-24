"""Benchmark and replay gate helpers for RPG Phase 24."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.rpg.replay_contracts import ReplayScenario, ReplaySnapshot, compare_snapshot_hashes, replay_report_payload, validate_snapshot

BENCHMARK_REPLAY_RUNTIME_SOURCE = "phase24_benchmark_replay_runtime_v1"
_REQUIRED_TURN_TARGET = 100


def build_benchmark_replay_report(
    summary: Mapping[str, object],
    *,
    expected_snapshot: ReplaySnapshot | None = None,
    actual_snapshot: ReplaySnapshot | None = None,
    scenario: ReplayScenario | None = None,
) -> dict[str, object]:
    """Build deterministic benchmark and replay-gate proof metadata."""

    rows = _sequence(summary.get("transcript_rows"))
    metrics = _benchmark_metrics(summary, len(rows))
    replay = _replay_gate(expected_snapshot, actual_snapshot, scenario)
    issues = tuple(_benchmark_issues(metrics, replay))
    return {
        "source": BENCHMARK_REPLAY_RUNTIME_SOURCE,
        "ready": not issues,
        "issues": list(issues),
        "benchmark": metrics,
        "replay_gate": replay,
    }


def _benchmark_metrics(summary: Mapping[str, object], row_count: int) -> dict[str, object]:
    requested = int(summary.get("requested_turns") or summary.get("turn_target") or row_count)
    completed = int(summary.get("completed_turns") or summary.get("turn_count") or row_count)
    blocking_avg = _float(summary.get("human_equivalent_avg_s") or summary.get("blocking_avg_s"))
    blocking_p95 = _float(summary.get("human_equivalent_p95_s") or summary.get("blocking_p95_s"))
    return {
        "requested_turns": requested,
        "completed_turns": completed,
        "transcript_rows": row_count,
        "turn_target_met": completed >= min(requested, _REQUIRED_TURN_TARGET),
        "blocking_avg_s": blocking_avg,
        "blocking_p95_s": blocking_p95,
        "has_latency_evidence": blocking_avg is not None or blocking_p95 is not None,
    }


def _replay_gate(
    expected: ReplaySnapshot | None,
    actual: ReplaySnapshot | None,
    scenario: ReplayScenario | None,
) -> dict[str, object]:
    if expected is None or actual is None or scenario is None:
        return {"configured": False, "passed": False, "issues": ["missing_replay_gate_inputs"]}
    comparison = compare_snapshot_hashes(expected, actual)
    issues = list(validate_snapshot(actual))
    if comparison["matches"] is not True:
        issues.append("snapshot_hash_mismatch")
    report = replay_report_payload(actual, scenario)
    return {
        "configured": True,
        "passed": not issues,
        "comparison": comparison,
        "report": report,
        "issues": issues,
    }


def _benchmark_issues(metrics: Mapping[str, object], replay: Mapping[str, object]) -> tuple[str, ...]:
    issues: list[str] = []
    if metrics.get("turn_target_met") is not True:
        issues.append("turn_target_not_met")
    if metrics.get("has_latency_evidence") is not True:
        issues.append("missing_latency_evidence")
    if replay.get("passed") is not True:
        issues.extend(str(item) for item in _sequence(replay.get("issues")))
    return tuple(issues)


def _float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return ()
