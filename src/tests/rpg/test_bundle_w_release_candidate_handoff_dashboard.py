from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zz_bundle_w_release_candidate_handoff_dashboard.pyfrag"
)


def _load_bundle_w_namespace():
    namespace = {"__name__": "_bundle_w_release_candidate_handoff_dashboard_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _handoff_payload(ready: bool = True):
    required = [
        {"file": "one-thousand-turn-readiness-aggregator-summary.json", "present": ready, "size_bytes": 100},
        {"file": "one-thousand-turn-readiness-dashboard-summary.json", "present": ready, "size_bytes": 100},
        {"file": "one-thousand-turn-preflight-profile-summary.json", "present": ready, "size_bytes": 100},
    ]
    missing = [] if ready else ["one-thousand-turn-preflight-profile-summary.json"]
    return {
        "format_version": "bundle_v_release_candidate_handoff_manifest_v1",
        "source": "bundle_v_release_candidate_handoff_manifest",
        "ok": ready,
        "release_candidate_handoff_ready": ready,
        "checks": {
            "release_candidate_dashboard_ready": ready,
            "live_result_release_candidate_ready": ready,
            "required_handoff_artifacts_present": ready,
            "focused_test_command_present": True,
            "preflight_command_present": True,
            "live_command_present": True,
        },
        "advisory_failures": [] if ready else ["required_handoff_artifacts_present"],
        "artifact_checklist": {
            "required": required,
            "optional_product": [
                {"file": "autoplay-campaign-report.html", "present": True, "size_bytes": 200},
                {"file": "autoplay-campaign-results.zip", "present": True, "size_bytes": 300},
            ],
            "missing_required": missing,
            "required_file_count": len(required),
            "present_required_file_count": len(required) if ready else len(required) - 1,
        },
        "commands": {
            "focused_test_suite": {"argv": ["python", "-m", "pytest"], "text": "python -m pytest src/tests/rpg/test_bundle_w_release_candidate_handoff_dashboard.py"},
            "preflight_1000": {"argv": ["python", "src/tests/rpg/autoplay_llm_campaign.py", "--preflight-profile", "preflight_1000"], "text": "python src/tests/rpg/autoplay_llm_campaign.py --preflight-profile preflight_1000"},
            "live_1000": {"argv": ["python", "src/tests/rpg/autoplay_llm_campaign.py", "--live-profile", "live_1000"], "text": "python src/tests/rpg/autoplay_llm_campaign.py --live-profile live_1000"},
        },
        "recommended_next_step": "archive_release_candidate_artifacts" if ready else "complete_release_candidate_handoff_artifacts",
    }


def test_bundle_w_dashboard_summary_reports_handoff_ready_state():
    namespace = _load_bundle_w_namespace()
    dashboard = namespace["_bundle_w_build_dashboard_summary"](_handoff_payload(True))

    assert dashboard["format_version"] == "bundle_w_release_candidate_handoff_dashboard_summary_v1"
    assert dashboard["source"] == "bundle_w_release_candidate_handoff_dashboard"
    assert dashboard["ok"] is True
    assert dashboard["status_label"] == "Handoff Ready"
    assert dashboard["status_class"] == "pass"
    assert dashboard["release_candidate_handoff_ready"] is True
    assert dashboard["required_file_count"] == 3
    assert dashboard["present_required_file_count"] == 3
    assert dashboard["missing_required_file_count"] == 0
    assert dashboard["artifact_completion_percent"] == 100
    assert dashboard["command_count"] == 3
    assert dashboard["recommended_next_step"] == "archive_release_candidate_artifacts"


def test_bundle_w_dashboard_summary_reports_blocked_state():
    namespace = _load_bundle_w_namespace()
    dashboard = namespace["_bundle_w_build_dashboard_summary"](_handoff_payload(False))

    assert dashboard["ok"] is False
    assert dashboard["status_label"] == "Handoff Blocked"
    assert dashboard["status_class"] == "warn"
    assert dashboard["release_candidate_handoff_ready"] is False
    assert dashboard["present_required_file_count"] == 2
    assert dashboard["missing_required_file_count"] == 1
    assert dashboard["artifact_completion_percent"] == 66
    assert dashboard["advisory_failure_count"] == 1
    assert dashboard["recommended_next_step"] == "complete_release_candidate_handoff_artifacts"


def test_bundle_w_writes_dashboard_when_handoff_manifest_is_exported(tmp_path):
    namespace = _load_bundle_w_namespace()
    original_write_text = namespace["_BUNDLE_W_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        (tmp_path / "one-thousand-turn-release-candidate-handoff-manifest.json").write_text(
            json.dumps(_handoff_payload(True)),
            encoding="utf-8",
        )

        dashboard_path = tmp_path / "one-thousand-turn-release-candidate-handoff-dashboard-summary.json"
        assert dashboard_path.exists()
        dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
        assert dashboard["ok"] is True
        assert dashboard["status_label"] == "Handoff Ready"
        assert dashboard["artifact_completion_percent"] == 100
    finally:
        Path.write_text = original_write_text


def test_bundle_w_injects_handoff_report_section_with_commands_and_collapsed_raw_json(tmp_path):
    namespace = _load_bundle_w_namespace()
    original_write_text = namespace["_BUNDLE_W_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        (tmp_path / "one-thousand-turn-release-candidate-handoff-manifest.json").write_text(
            json.dumps(_handoff_payload(True)),
            encoding="utf-8",
        )
        report_path = tmp_path / "autoplay-campaign-report.html"
        report_path.write_text(
            "<html><body><h1>Autoplay Campaign Report</h1><main><p>Body</p></main></body></html>",
            encoding="utf-8",
        )
        rendered = report_path.read_text(encoding="utf-8")

        assert 'id="bundle-w-release-candidate-handoff-dashboard"' in rendered
        assert "1000-Turn Release Candidate Handoff" in rendered
        assert "Handoff Ready" in rendered
        assert "Artifacts: 3/3 required present (100%)." in rendered
        assert "python src/tests/rpg/autoplay_llm_campaign.py --preflight-profile preflight_1000" in rendered
        assert "python src/tests/rpg/autoplay_llm_campaign.py --live-profile live_1000" in rendered
        assert '<details class="bundle-w-raw-details">' in rendered
        raw_start = rendered.index('<details class="bundle-w-raw-details">')
        raw_open = rendered[raw_start : rendered.index(">", raw_start) + 1]
        assert " open" not in raw_open
        assert "<p>Body</p>" in rendered
    finally:
        Path.write_text = original_write_text
