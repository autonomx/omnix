from __future__ import annotations

from app.rpg.benchmark_replay_runtime import build_benchmark_replay_report
from app.rpg.replay_contracts import ReplaySnapshot, build_regression_scenario


def _snapshot() -> ReplaySnapshot:
    return ReplaySnapshot(
        "snap-100",
        100,
        42,
        {"rng": 9},
        {"world": {}, "player": {}, "quests": {}, "map": {}, "inventory": {}},
    )


def test_phase24_benchmark_replay_gate_passes() -> None:
    snapshot = _snapshot()
    report = build_benchmark_replay_report(
        {
            "requested_turns": 100,
            "completed_turns": 100,
            "human_equivalent_avg_s": 4.8,
            "transcript_rows": [{} for _ in range(100)],
        },
        expected_snapshot=snapshot,
        actual_snapshot=snapshot,
        scenario=build_regression_scenario("p24", 42, ["look", "travel"]),
    )

    assert report["ready"] is True
    assert report["benchmark"]["turn_target_met"] is True
    assert report["replay_gate"]["passed"] is True


def test_phase24_benchmark_replay_gate_flags_missing_inputs() -> None:
    report = build_benchmark_replay_report({"completed_turns": 10, "transcript_rows": []})

    assert report["ready"] is False
    assert "turn_target_not_met" in report["issues"]
    assert "missing_latency_evidence" in report["issues"]
    assert "missing_replay_gate_inputs" in report["issues"]


def test_phase24_benchmark_replay_gate_flags_hash_mismatch() -> None:
    expected = _snapshot()
    actual = ReplaySnapshot(
        "snap-100",
        100,
        42,
        {"rng": 10},
        {"world": {}, "player": {}, "quests": {}, "map": {}, "inventory": {}},
    )
    report = build_benchmark_replay_report(
        {"requested_turns": 100, "completed_turns": 100, "blocking_avg_s": 5.0},
        expected_snapshot=expected,
        actual_snapshot=actual,
        scenario=build_regression_scenario("p24", 42, ["look"]),
    )

    assert report["ready"] is False
    assert "snapshot_hash_mismatch" in report["issues"]
