from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zz_bundle_t_live_1000_result_gate.pyfrag"
)


def _load_bundle_t_namespace():
    namespace = {"__name__": "_bundle_t_live_1000_result_gate_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _passing_artifacts():
    return {
        "one-thousand-turn-live-run-profile-summary.json": {
            "ok": True,
            "ready_to_start_live_1000_turn_run": True,
        },
        "one-thousand-turn-preflight-result-summary.json": {
            "ok": True,
            "promote_to_live_1000_turn_run": True,
        },
        "one-thousand-turn-readiness-dashboard-summary.json": {
            "ok": True,
            "status_label": "Live Ready",
        },
        "one-thousand-turn-readiness-aggregator-summary.json": {
            "ok": True,
            "failing_required_gates": [],
            "missing_required_gates": [],
        },
        "summary.json": {
            "requested_turns": 1000,
            "completed_turns": 1000,
            "runtime_error_count": 0,
            "unresolved_final_background_jobs": 0,
            "campaign_report_present": True,
            "zipped_results_present": True,
        },
        "performance-summary.json": {
            "blocking_turn_p95_seconds": 7.5,
            "background_drain_seconds": 90,
        },
        "progress-quality-summary.json": {
            "player_agent_fallback_rate": 0.10,
            "meaningful_progress_rate": 0.25,
        },
        "artifact-manifest-digest.json": {"ok": True, "invariant_ok": True},
        "transcript-payload-budget-summary.json": {"ok": True},
    }


def _write_live_artifacts_in_final_export_order(tmp_path: Path, artifacts: dict):
    # Write broad run artifacts first because earlier Bundle O/P/Q/R/S decorators
    # may regenerate readiness sidecars when summary/manifest/performance files land.
    # Then write final readiness/profile artifacts last so Bundle T evaluates the
    # same final artifact ordering used by real autoplay exports.
    for file_name in (
        "summary.json",
        "performance-summary.json",
        "progress-quality-summary.json",
        "artifact-manifest-digest.json",
        "transcript-payload-budget-summary.json",
        "one-thousand-turn-preflight-result-summary.json",
        "one-thousand-turn-live-run-profile-summary.json",
        "one-thousand-turn-readiness-aggregator-summary.json",
        "one-thousand-turn-readiness-dashboard-summary.json",
    ):
        (tmp_path / file_name).write_text(json.dumps(artifacts[file_name]), encoding="utf-8")


def test_bundle_t_live_result_marks_release_candidate_when_all_checks_pass():
    namespace = _load_bundle_t_namespace()
    result = namespace["_bundle_t_evaluate_live_1000_result"](_passing_artifacts())

    assert result["format_version"] == "bundle_t_live_1000_result_summary_v1"
    assert result["source"] == "bundle_t_live_1000_result_gate"
    assert result["ok"] is True
    assert result["advisory_only"] is True
    assert result["release_candidate_ready"] is True
    assert result["advisory_failures"] == []
    assert result["checks"]["live_profile_ready"] is True
    assert result["checks"]["preflight_promoted_live_run"] is True
    assert result["checks"]["completed_target_turns"] is True
    assert result["checks"]["no_required_gate_failures"] is True
    assert result["checks"]["campaign_report_artifact_present"] is True
    assert result["checks"]["zipped_results_artifact_present"] is True
    assert result["recommended_next_step"] == "mark_1000_turn_release_candidate"


def test_bundle_t_blocks_release_candidate_for_gate_runtime_and_artifact_failures():
    namespace = _load_bundle_t_namespace()
    artifacts = _passing_artifacts()
    artifacts["one-thousand-turn-live-run-profile-summary.json"]["ready_to_start_live_1000_turn_run"] = False
    artifacts["one-thousand-turn-preflight-result-summary.json"]["promote_to_live_1000_turn_run"] = False
    artifacts["one-thousand-turn-readiness-aggregator-summary.json"]["failing_required_gates"] = ["memory_state_compression"]
    artifacts["summary.json"]["runtime_error_count"] = 1
    artifacts["summary.json"]["unresolved_final_background_jobs"] = 2
    artifacts["summary.json"]["campaign_report_present"] = False
    artifacts["summary.json"]["zipped_results_present"] = False

    result = namespace["_bundle_t_evaluate_live_1000_result"](artifacts)

    assert result["ok"] is False
    assert result["release_candidate_ready"] is False
    assert "live_profile_ready" in result["advisory_failures"]
    assert "preflight_promoted_live_run" in result["advisory_failures"]
    assert "no_required_gate_failures" in result["advisory_failures"]
    assert "no_runtime_errors" in result["advisory_failures"]
    assert "no_unresolved_background_jobs" in result["advisory_failures"]
    assert "campaign_report_artifact_present" in result["advisory_failures"]
    assert "zipped_results_artifact_present" in result["advisory_failures"]
    assert result["recommended_next_step"] == "fix_live_1000_result_failures_before_release_candidate"


def test_bundle_t_blocks_release_candidate_for_performance_progress_and_transcript_budget():
    namespace = _load_bundle_t_namespace()
    artifacts = _passing_artifacts()
    artifacts["performance-summary.json"]["blocking_turn_p95_seconds"] = 15.0
    artifacts["performance-summary.json"]["background_drain_seconds"] = 220.0
    artifacts["progress-quality-summary.json"]["player_agent_fallback_rate"] = 0.50
    artifacts["progress-quality-summary.json"]["meaningful_progress_rate"] = 0.05
    artifacts["transcript-payload-budget-summary.json"]["ok"] = False
    artifacts["summary.json"]["report_regression_warning_count"] = 1

    result = namespace["_bundle_t_evaluate_live_1000_result"](artifacts)

    assert result["ok"] is False
    assert "blocking_turn_p95_within_live_budget" in result["advisory_failures"]
    assert "background_drain_within_live_budget" in result["advisory_failures"]
    assert "player_agent_fallback_rate_within_budget" in result["advisory_failures"]
    assert "meaningful_progress_rate_within_budget" in result["advisory_failures"]
    assert "transcript_budget_ok" in result["advisory_failures"]
    assert "no_report_regression_warnings" in result["advisory_failures"]


def test_bundle_t_artifact_scanner_detects_report_and_zip_files(tmp_path):
    namespace = _load_bundle_t_namespace()
    _write_live_artifacts_in_final_export_order(tmp_path, _passing_artifacts())
    (tmp_path / "autoplay-campaign-report.html").write_text("<html>report</html>", encoding="utf-8")
    (tmp_path / "autoplay-campaign-results.zip").write_bytes(b"PK\x03\x04fake")

    artifacts = namespace["_bundle_t_artifacts_from_result_dir"](tmp_path)
    result = namespace["_bundle_t_evaluate_live_1000_result"](artifacts)

    assert artifacts["autoplay-campaign-report.html"]["present"] is True
    assert artifacts["autoplay-campaign-results.zip"]["present"] is True
    assert result["ok"] is True
    assert result["metrics"]["campaign_report_size_bytes"] > 0
    assert result["metrics"]["zipped_results_size_bytes"] > 0


def test_bundle_t_writes_summary_when_live_artifacts_are_exported(tmp_path):
    namespace = _load_bundle_t_namespace()
    original_write_text = namespace["_BUNDLE_T_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        _write_live_artifacts_in_final_export_order(tmp_path, _passing_artifacts())

        summary_path = tmp_path / "one-thousand-turn-live-result-summary.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["ok"] is True
        assert summary["release_candidate_ready"] is True
        assert summary["checks"]["completed_target_turns"] is True
        assert summary["recommended_next_step"] == "mark_1000_turn_release_candidate"
    finally:
        Path.write_text = original_write_text
