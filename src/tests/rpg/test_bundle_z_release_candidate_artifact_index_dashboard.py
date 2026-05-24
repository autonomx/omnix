from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zz_bundle_z_release_candidate_artifact_index_dashboard.pyfrag"
)


def _load_bundle_z_namespace():
    namespace = {"__name__": "_bundle_z_release_candidate_artifact_index_dashboard_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _artifact_index_payload(ready: bool = True):
    tracked = [
        {
            "file": "one-thousand-turn-release-candidate-runbook.md",
            "present": True,
            "required_for_archive": True,
            "size_bytes": 123,
            "sha256": "a" * 64,
        },
        {
            "file": "autoplay-campaign-results.zip",
            "present": ready,
            "required_for_archive": False,
            "size_bytes": 456 if ready else 0,
            "sha256": "b" * 64 if ready else "",
        },
        {
            "file": "one-thousand-turn-release-candidate-runbook-summary.json",
            "present": ready,
            "required_for_archive": True,
            "size_bytes": 111 if ready else 0,
            "sha256": "c" * 64 if ready else "",
        },
    ]
    present_count = len([entry for entry in tracked if entry["present"]])
    return {
        "format_version": "bundle_y_release_candidate_artifact_index_v1",
        "source": "bundle_y_release_candidate_artifact_index",
        "ok": ready,
        "archive_index_ready": ready,
        "advisory_only": True,
        "checks": {
            "runbook_summary_ready": ready,
            "required_archive_artifacts_present": ready,
            "at_least_one_product_artifact_present": ready,
            "archive_digest_available": ready,
            "tracked_file_entries_present": True,
        },
        "advisory_failures": [] if ready else ["required_archive_artifacts_present"],
        "missing_required_archive_artifacts": [] if ready else ["one-thousand-turn-release-candidate-runbook-summary.json"],
        "archive_digest_sha256": "d" * 64 if ready else "",
        "tracked_files": tracked,
        "metrics": {
            "tracked_file_count": len(tracked),
            "present_tracked_file_count": present_count,
            "missing_required_archive_file_count": 0 if ready else 1,
            "total_present_bytes": sum(entry["size_bytes"] for entry in tracked if entry["present"]),
        },
        "recommended_next_step": "archive_release_candidate_artifact_index" if ready else "complete_release_candidate_archive_artifacts",
    }


def test_bundle_z_dashboard_summary_reports_archive_ready_state():
    namespace = _load_bundle_z_namespace()
    dashboard = namespace["_bundle_z_build_dashboard_summary"](_artifact_index_payload(True))

    assert dashboard["format_version"] == "bundle_z_release_candidate_artifact_index_dashboard_summary_v1"
    assert dashboard["source"] == "bundle_z_release_candidate_artifact_index_dashboard"
    assert dashboard["ok"] is True
    assert dashboard["status_label"] == "Archive Index Ready"
    assert dashboard["status_class"] == "pass"
    assert dashboard["archive_index_ready"] is True
    assert dashboard["archive_digest_sha256"] == "d" * 64
    assert dashboard["tracked_file_count"] == 3
    assert dashboard["present_tracked_file_count"] == 3
    assert dashboard["tracked_completion_percent"] == 100
    assert dashboard["missing_required_archive_artifact_count"] == 0
    assert dashboard["recommended_next_step"] == "archive_release_candidate_artifact_index"


def test_bundle_z_dashboard_summary_reports_blocked_state():
    namespace = _load_bundle_z_namespace()
    dashboard = namespace["_bundle_z_build_dashboard_summary"](_artifact_index_payload(False))

    assert dashboard["ok"] is False
    assert dashboard["status_label"] == "Archive Index Blocked"
    assert dashboard["status_class"] == "warn"
    assert dashboard["archive_index_ready"] is False
    assert dashboard["tracked_file_count"] == 3
    assert dashboard["present_tracked_file_count"] == 1
    assert dashboard["tracked_completion_percent"] == 33
    assert dashboard["missing_required_archive_artifact_count"] == 1
    assert dashboard["missing_required_archive_artifacts"] == ["one-thousand-turn-release-candidate-runbook-summary.json"]
    assert dashboard["advisory_failure_count"] == 1
    assert dashboard["recommended_next_step"] == "complete_release_candidate_archive_artifacts"


def test_bundle_z_writes_dashboard_when_artifact_index_is_exported(tmp_path):
    namespace = _load_bundle_z_namespace()
    original_write_text = namespace["_BUNDLE_Z_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        (tmp_path / "one-thousand-turn-release-candidate-artifact-index.json").write_text(
            json.dumps(_artifact_index_payload(True)),
            encoding="utf-8",
        )

        dashboard_path = tmp_path / "one-thousand-turn-release-candidate-artifact-index-dashboard-summary.json"
        assert dashboard_path.exists()
        dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
        assert dashboard["ok"] is True
        assert dashboard["status_label"] == "Archive Index Ready"
        assert dashboard["archive_digest_sha256"] == "d" * 64
    finally:
        Path.write_text = original_write_text


def test_bundle_z_injects_artifact_index_report_section_with_digest_and_collapsed_raw_json(tmp_path):
    namespace = _load_bundle_z_namespace()
    original_write_text = namespace["_BUNDLE_Z_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        (tmp_path / "one-thousand-turn-release-candidate-artifact-index.json").write_text(
            json.dumps(_artifact_index_payload(True)),
            encoding="utf-8",
        )
        report_path = tmp_path / "autoplay-campaign-report.html"
        report_path.write_text(
            "<html><body><h1>Autoplay Campaign Report</h1><main><p>Body</p></main></body></html>",
            encoding="utf-8",
        )
        rendered = report_path.read_text(encoding="utf-8")

        assert 'id="bundle-z-release-candidate-artifact-index-dashboard"' in rendered
        assert "1000-Turn Artifact Index" in rendered
        assert "Archive Index Ready" in rendered
        assert "Artifacts: 3/3 tracked present (100%)." in rendered
        assert "archive_release_candidate_artifact_index" in rendered
        assert "one-thousand-turn-release-candidate-runbook.md" in rendered
        assert "autoplay-campaign-results.zip" in rendered
        assert ("d" * 64) in rendered
        assert '<details class="bundle-z-raw-details">' in rendered
        raw_start = rendered.index('<details class="bundle-z-raw-details">')
        raw_open = rendered[raw_start : rendered.index(">", raw_start) + 1]
        assert " open" not in raw_open
        assert "<p>Body</p>" in rendered
    finally:
        Path.write_text = original_write_text
