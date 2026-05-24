from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zz_bundle_x_release_candidate_runbook.pyfrag"
)


def _load_bundle_x_namespace():
    namespace = {"__name__": "_bundle_x_release_candidate_runbook_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _handoff_payload(ready: bool = True):
    missing = [] if ready else ["one-thousand-turn-live-result-summary.json"]
    return {
        "format_version": "bundle_v_release_candidate_handoff_manifest_v1",
        "source": "bundle_v_release_candidate_handoff_manifest",
        "ok": ready,
        "release_candidate_handoff_ready": ready,
        "artifact_checklist": {
            "required": [
                {"file": "one-thousand-turn-readiness-aggregator-summary.json", "present": True, "size_bytes": 100},
                {"file": "one-thousand-turn-live-result-summary.json", "present": ready, "size_bytes": 100 if ready else 0},
                {"file": "one-thousand-turn-release-candidate-dashboard-summary.json", "present": True, "size_bytes": 100},
            ],
            "optional_product": [
                {"file": "autoplay-campaign-report.html", "present": True, "size_bytes": 200},
                {"file": "autoplay-campaign-results.zip", "present": True, "size_bytes": 300},
            ],
            "missing_required": missing,
            "required_file_count": 3,
            "present_required_file_count": 3 if ready else 2,
        },
        "commands": {
            "focused_test_suite": {
                "argv": ["python", "-m", "pytest"],
                "text": "python -m pytest src/tests/rpg/test_bundle_x_release_candidate_runbook.py",
            },
            "preflight_1000": {
                "argv": ["python", "src/tests/rpg/autoplay_llm_campaign.py", "--preflight-profile", "preflight_1000"],
                "text": "python src/tests/rpg/autoplay_llm_campaign.py --preflight-profile preflight_1000",
            },
            "live_1000": {
                "argv": ["python", "src/tests/rpg/autoplay_llm_campaign.py", "--live-profile", "live_1000"],
                "text": "python src/tests/rpg/autoplay_llm_campaign.py --live-profile live_1000",
            },
        },
        "recommended_next_step": "archive_release_candidate_artifacts" if ready else "complete_release_candidate_handoff_artifacts",
    }


def _dashboard_payload(ready: bool = True):
    return {
        "format_version": "bundle_w_release_candidate_handoff_dashboard_summary_v1",
        "source": "bundle_w_release_candidate_handoff_dashboard",
        "ok": ready,
        "status_label": "Handoff Ready" if ready else "Handoff Blocked",
        "status_class": "pass" if ready else "warn",
        "release_candidate_handoff_ready": ready,
        "artifact_completion_percent": 100 if ready else 66,
    }


def test_bundle_x_builds_markdown_runbook_with_artifacts_and_commands():
    namespace = _load_bundle_x_namespace()
    markdown = namespace["_bundle_x_build_runbook_markdown"](_handoff_payload(True), _dashboard_payload(True))

    assert markdown.startswith("# 1000-Turn Release Candidate Runbook")
    assert "**Status:** Handoff Ready" in markdown
    assert "**Recommended next step:** `archive_release_candidate_artifacts`" in markdown
    assert "| `one-thousand-turn-readiness-aggregator-summary.json` | required | present | 100 |" in markdown
    assert "| `autoplay-campaign-results.zip` | optional_product | present | 300 |" in markdown
    assert "```powershell" in markdown
    assert "python src/tests/rpg/autoplay_llm_campaign.py --preflight-profile preflight_1000" in markdown
    assert "python src/tests/rpg/autoplay_llm_campaign.py --live-profile live_1000" in markdown
    assert "Do not run the live profile unless the preflight result gate promotes it." in markdown


def test_bundle_x_summary_passes_when_handoff_dashboard_and_runbook_are_ready(tmp_path):
    namespace = _load_bundle_x_namespace()
    handoff = _handoff_payload(True)
    dashboard = _dashboard_payload(True)
    markdown = namespace["_bundle_x_build_runbook_markdown"](handoff, dashboard)
    (tmp_path / "one-thousand-turn-release-candidate-runbook.md").write_text(markdown, encoding="utf-8")

    summary = namespace["_bundle_x_build_summary"](tmp_path, handoff, dashboard)

    assert summary["format_version"] == "bundle_x_release_candidate_runbook_summary_v1"
    assert summary["source"] == "bundle_x_release_candidate_runbook"
    assert summary["ok"] is True
    assert summary["advisory_only"] is True
    assert summary["runbook_ready"] is True
    assert summary["advisory_failures"] == []
    assert summary["checks"]["handoff_manifest_present"] is True
    assert summary["checks"]["handoff_dashboard_present"] is True
    assert summary["checks"]["handoff_ready"] is True
    assert summary["checks"]["required_artifacts_present"] is True
    assert summary["checks"]["focused_test_command_present"] is True
    assert summary["checks"]["preflight_command_present"] is True
    assert summary["checks"]["live_command_present"] is True
    assert summary["checks"]["runbook_markdown_written"] is True
    assert summary["recommended_next_step"] == "archive_release_candidate_runbook"


def test_bundle_x_summary_reports_missing_or_blocked_inputs(tmp_path):
    namespace = _load_bundle_x_namespace()
    handoff = _handoff_payload(False)
    dashboard = _dashboard_payload(False)

    summary = namespace["_bundle_x_build_summary"](tmp_path, handoff, dashboard)

    assert summary["ok"] is False
    assert summary["runbook_ready"] is False
    assert "handoff_ready" in summary["advisory_failures"]
    assert "required_artifacts_present" in summary["advisory_failures"]
    assert "runbook_markdown_written" in summary["advisory_failures"]
    assert summary["metrics"]["missing_required_file_count"] == 1
    assert summary["recommended_next_step"] == "complete_release_candidate_runbook_inputs"


def test_bundle_x_writes_runbook_and_summary_when_inputs_are_exported(tmp_path):
    namespace = _load_bundle_x_namespace()
    original_write_text = namespace["_BUNDLE_X_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        (tmp_path / "one-thousand-turn-release-candidate-handoff-manifest.json").write_text(
            json.dumps(_handoff_payload(True)),
            encoding="utf-8",
        )
        (tmp_path / "one-thousand-turn-release-candidate-handoff-dashboard-summary.json").write_text(
            json.dumps(_dashboard_payload(True)),
            encoding="utf-8",
        )

        runbook_path = tmp_path / "one-thousand-turn-release-candidate-runbook.md"
        summary_path = tmp_path / "one-thousand-turn-release-candidate-runbook-summary.json"
        assert runbook_path.exists()
        assert summary_path.exists()
        markdown = runbook_path.read_text(encoding="utf-8")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert "# 1000-Turn Release Candidate Runbook" in markdown
        assert "python src/tests/rpg/autoplay_llm_campaign.py --live-profile live_1000" in markdown
        assert summary["ok"] is True
        assert summary["runbook_ready"] is True
        assert summary["metrics"]["runbook_size_bytes"] > 0
    finally:
        Path.write_text = original_write_text
