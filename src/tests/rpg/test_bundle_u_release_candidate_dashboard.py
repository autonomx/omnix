from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zz_bundle_u_release_candidate_dashboard.pyfrag"
)


def _load_bundle_u_namespace():
    namespace = {"__name__": "_bundle_u_release_candidate_dashboard_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _live_result_payload(ready: bool = True):
    checks = {
        "live_profile_ready": True,
        "preflight_promoted_live_run": True,
        "completed_target_turns": True,
        "no_runtime_errors": True,
        "campaign_report_artifact_present": True,
        "zipped_results_artifact_present": True,
    }
    failures = []
    if not ready:
        checks["no_runtime_errors"] = False
        failures = ["no_runtime_errors"]
    return {
        "format_version": "bundle_t_live_1000_result_summary_v1",
        "source": "bundle_t_live_1000_result_gate",
        "ok": ready,
        "release_candidate_ready": ready,
        "checks": checks,
        "advisory_failures": failures,
        "metrics": {
            "completed_turns": 1000,
            "runtime_error_count": 0 if ready else 1,
            "blocking_turn_p95_seconds": 7.5,
            "meaningful_progress_rate": 0.25,
        },
        "recommended_next_step": "mark_1000_turn_release_candidate" if ready else "fix_live_1000_result_failures_before_release_candidate",
    }


def test_bundle_u_dashboard_summary_reports_release_candidate_ready_state():
    namespace = _load_bundle_u_namespace()
    dashboard = namespace["_bundle_u_build_dashboard_summary"](_live_result_payload(True))

    assert dashboard["format_version"] == "bundle_u_release_candidate_dashboard_summary_v1"
    assert dashboard["source"] == "bundle_u_release_candidate_dashboard"
    assert dashboard["ok"] is True
    assert dashboard["status_label"] == "Release Candidate Ready"
    assert dashboard["status_class"] == "pass"
    assert dashboard["release_candidate_ready"] is True
    assert dashboard["check_count"] == 6
    assert dashboard["passing_check_count"] == 6
    assert dashboard["failing_check_count"] == 0
    assert dashboard["completion_percent"] == 100
    assert dashboard["recommended_next_step"] == "mark_1000_turn_release_candidate"


def test_bundle_u_dashboard_summary_reports_blocked_state():
    namespace = _load_bundle_u_namespace()
    dashboard = namespace["_bundle_u_build_dashboard_summary"](_live_result_payload(False))

    assert dashboard["ok"] is False
    assert dashboard["status_label"] == "Release Candidate Blocked"
    assert dashboard["status_class"] == "warn"
    assert dashboard["release_candidate_ready"] is False
    assert dashboard["passing_check_count"] == 5
    assert dashboard["failing_check_count"] == 1
    assert dashboard["advisory_failure_count"] == 1
    assert dashboard["advisory_failures"] == ["no_runtime_errors"]
    assert dashboard["recommended_next_step"] == "fix_live_1000_result_failures_before_release_candidate"


def test_bundle_u_writes_dashboard_when_live_result_is_exported(tmp_path):
    namespace = _load_bundle_u_namespace()
    original_write_text = namespace["_BUNDLE_U_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        (tmp_path / "one-thousand-turn-live-result-summary.json").write_text(
            json.dumps(_live_result_payload(True)),
            encoding="utf-8",
        )

        dashboard_path = tmp_path / "one-thousand-turn-release-candidate-dashboard-summary.json"
        assert dashboard_path.exists()
        dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
        assert dashboard["ok"] is True
        assert dashboard["status_label"] == "Release Candidate Ready"
        assert dashboard["completion_percent"] == 100
    finally:
        Path.write_text = original_write_text


def test_bundle_u_injects_release_candidate_report_section_with_collapsed_raw_json(tmp_path):
    namespace = _load_bundle_u_namespace()
    original_write_text = namespace["_BUNDLE_U_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        (tmp_path / "one-thousand-turn-live-result-summary.json").write_text(
            json.dumps(_live_result_payload(True)),
            encoding="utf-8",
        )
        report_path = tmp_path / "autoplay-campaign-report.html"
        report_path.write_text(
            "<html><body><h1>Autoplay Campaign Report</h1><main><p>Body</p></main></body></html>",
            encoding="utf-8",
        )
        rendered = report_path.read_text(encoding="utf-8")

        assert 'id="bundle-u-release-candidate-dashboard"' in rendered
        assert "1000-Turn Release Candidate Dashboard" in rendered
        assert "Release Candidate Ready" in rendered
        assert "Progress: 6/6 checks passing (100%)." in rendered
        assert "mark_1000_turn_release_candidate" in rendered
        assert '<details class="bundle-u-raw-details">' in rendered
        raw_start = rendered.index('<details class="bundle-u-raw-details">')
        raw_open = rendered[raw_start : rendered.index(">", raw_start) + 1]
        assert " open" not in raw_open
        assert "<p>Body</p>" in rendered
    finally:
        Path.write_text = original_write_text
