from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zz_bundle_r_1000_turn_preflight_result_gate.pyfrag"
)


def _load_bundle_r_namespace():
    namespace = {"__name__": "_bundle_r_1000_turn_preflight_result_gate_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _passing_artifacts():
    return {
        "one-thousand-turn-preflight-profile-summary.json": {"ok": True, "target_turns": 1000},
        "one-thousand-turn-readiness-aggregator-summary.json": {
            "ok": True,
            "ready_for_1000_turn_preflight": True,
            "failing_required_gates": [],
            "missing_required_gates": [],
        },
        "one-thousand-turn-readiness-dashboard-summary.json": {
            "ok": True,
            "status_label": "Preflight Ready",
        },
        "summary.json": {
            "requested_turns": 1000,
            "completed_turns": 1000,
            "runtime_error_count": 0,
            "unresolved_final_background_jobs": 0,
        },
        "performance-summary.json": {
            "blocking_turn_p95_seconds": 6.5,
            "background_drain_seconds": 80,
        },
        "progress-quality-summary.json": {
            "player_agent_fallback_rate": 0.10,
            "meaningful_progress_rate": 0.25,
        },
        "artifact-manifest-digest.json": {"ok": True, "invariant_ok": True},
    }


def test_bundle_r_preflight_result_promotes_when_all_checks_pass():
    namespace = _load_bundle_r_namespace()
    result = namespace["_bundle_r_evaluate_1000_turn_preflight_result"](_passing_artifacts())

    assert result["format_version"] == "bundle_r_1000_turn_preflight_result_summary_v1"
    assert result["source"] == "bundle_r_1000_turn_preflight_result_gate"
    assert result["ok"] is True
    assert result["advisory_only"] is True
    assert result["promote_to_live_1000_turn_run"] is True
    assert result["advisory_failures"] == []
    assert result["checks"]["preflight_profile_ready"] is True
    assert result["checks"]["readiness_aggregator_ready"] is True
    assert result["checks"]["readiness_dashboard_ready"] is True
    assert result["checks"]["completed_target_turns"] is True
    assert result["checks"]["no_required_gate_failures"] is True
    assert result["checks"]["blocking_turn_p95_within_budget"] is True
    assert result["checks"]["meaningful_progress_rate_within_budget"] is True
    assert result["recommended_next_step"] == "promote_to_live_1000_turn_run"


def test_bundle_r_blocks_promotion_for_gate_and_runtime_failures():
    namespace = _load_bundle_r_namespace()
    artifacts = _passing_artifacts()
    artifacts["one-thousand-turn-readiness-aggregator-summary.json"]["ready_for_1000_turn_preflight"] = False
    artifacts["one-thousand-turn-readiness-aggregator-summary.json"]["failing_required_gates"] = ["memory_state_compression"]
    artifacts["summary.json"]["runtime_error_count"] = 1
    artifacts["summary.json"]["unresolved_final_background_jobs"] = 2

    result = namespace["_bundle_r_evaluate_1000_turn_preflight_result"](artifacts)

    assert result["ok"] is False
    assert result["promote_to_live_1000_turn_run"] is False
    assert "readiness_aggregator_ready" in result["advisory_failures"]
    assert "no_required_gate_failures" in result["advisory_failures"]
    assert "no_runtime_errors" in result["advisory_failures"]
    assert "no_unresolved_background_jobs" in result["advisory_failures"]
    assert result["recommended_next_step"] == "fix_preflight_result_failures_before_live_1000_turn_run"


def test_bundle_r_blocks_promotion_for_performance_and_progress_thresholds():
    namespace = _load_bundle_r_namespace()
    artifacts = _passing_artifacts()
    artifacts["performance-summary.json"]["blocking_turn_p95_seconds"] = 12.0
    artifacts["performance-summary.json"]["background_drain_seconds"] = 140.0
    artifacts["progress-quality-summary.json"]["player_agent_fallback_rate"] = 0.50
    artifacts["progress-quality-summary.json"]["meaningful_progress_rate"] = 0.05

    result = namespace["_bundle_r_evaluate_1000_turn_preflight_result"](artifacts)

    assert result["ok"] is False
    assert "blocking_turn_p95_within_budget" in result["advisory_failures"]
    assert "background_drain_within_budget" in result["advisory_failures"]
    assert "player_agent_fallback_rate_within_budget" in result["advisory_failures"]
    assert "meaningful_progress_rate_within_budget" in result["advisory_failures"]


def test_bundle_r_writes_summary_when_preflight_artifacts_are_exported(tmp_path):
    namespace = _load_bundle_r_namespace()
    original_write_text = namespace["_BUNDLE_R_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        for file_name, payload in _passing_artifacts().items():
            (tmp_path / file_name).write_text(json.dumps(payload), encoding="utf-8")

        summary_path = tmp_path / "one-thousand-turn-preflight-result-summary.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["ok"] is True
        assert summary["promote_to_live_1000_turn_run"] is True
        assert summary["checks"]["completed_target_turns"] is True
        assert summary["recommended_next_step"] == "promote_to_live_1000_turn_run"
    finally:
        Path.write_text = original_write_text
