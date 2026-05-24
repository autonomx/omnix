from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zz_bundle_ab_focused_suite_registry_dashboard.pyfrag"
)


def _load_bundle_ab_namespace():
    namespace = {"__name__": "_bundle_ab_focused_suite_registry_dashboard_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _registry_payload(ready: bool = True):
    tests = [
        "src/tests/rpg/test_bundle_e_product_report_rendering.py",
        "src/tests/rpg/test_bundle_v_release_candidate_handoff_manifest.py",
        "src/tests/rpg/test_bundle_z_release_candidate_artifact_index_dashboard.py",
        "src/tests/rpg/test_bundle_ab_focused_suite_registry_dashboard.py",
    ]
    command = ["python", "-m", "pytest", *tests]
    return {
        "format_version": "bundle_aa_focused_suite_registry_summary_v1",
        "source": "bundle_aa_focused_suite_registry",
        "ok": ready,
        "focused_suite_registry_ready": ready,
        "checks": {
            "registry_has_expected_range": ready,
            "registry_test_count_expected": ready,
            "registry_has_no_duplicates": True,
            "registry_files_exist": True,
            "command_starts_with_pytest": True,
            "handoff_command_matches_registry": ready,
        },
        "advisory_failures": [] if ready else ["handoff_command_matches_registry"],
        "metrics": {
            "test_file_count": len(tests),
            "missing_test_file_count": 0,
            "duplicate_test_file_count": 0,
            "command_arg_count": len(command),
            "handoff_command_arg_count": len(command) if ready else 4,
        },
        "test_files": tests,
        "canonical_command": {"argv": command, "text": " ".join(command)},
        "recommended_next_step": "use_canonical_e_ab_focused_suite_command" if ready else "fix_focused_suite_registry_drift",
    }


def test_bundle_ab_dashboard_summary_reports_synced_state():
    namespace = _load_bundle_ab_namespace()
    dashboard = namespace["_bundle_ab_build_dashboard_summary"](_registry_payload(True))

    assert dashboard["format_version"] == "bundle_ab_focused_suite_registry_dashboard_summary_v1"
    assert dashboard["source"] == "bundle_ab_focused_suite_registry_dashboard"
    assert dashboard["ok"] is True
    assert dashboard["status_label"] == "Focused Suite Synced"
    assert dashboard["status_class"] == "pass"
    assert dashboard["focused_suite_registry_ready"] is True
    assert dashboard["test_file_count"] == 4
    assert dashboard["missing_test_file_count"] == 0
    assert dashboard["duplicate_test_file_count"] == 0
    assert dashboard["advisory_failure_count"] == 0
    assert dashboard["first_test_file"] == "src/tests/rpg/test_bundle_e_product_report_rendering.py"
    assert dashboard["last_test_file"] == "src/tests/rpg/test_bundle_ab_focused_suite_registry_dashboard.py"
    assert "python -m pytest" in dashboard["canonical_command_text"]
    assert dashboard["recommended_next_step"] == "use_canonical_e_ab_focused_suite_command"


def test_bundle_ab_dashboard_summary_reports_drift_state():
    namespace = _load_bundle_ab_namespace()
    dashboard = namespace["_bundle_ab_build_dashboard_summary"](_registry_payload(False))

    assert dashboard["ok"] is False
    assert dashboard["status_label"] == "Focused Suite Drift"
    assert dashboard["status_class"] == "warn"
    assert dashboard["focused_suite_registry_ready"] is False
    assert dashboard["advisory_failure_count"] == 1
    assert dashboard["advisory_failures"] == ["handoff_command_matches_registry"]
    assert dashboard["recommended_next_step"] == "fix_focused_suite_registry_drift"


def test_bundle_ab_writes_dashboard_when_registry_summary_is_exported(tmp_path):
    namespace = _load_bundle_ab_namespace()
    original_write_text = namespace["_BUNDLE_AB_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        (tmp_path / "one-thousand-turn-focused-suite-registry-summary.json").write_text(
            json.dumps(_registry_payload(True)),
            encoding="utf-8",
        )

        dashboard_path = tmp_path / "one-thousand-turn-focused-suite-registry-dashboard-summary.json"
        assert dashboard_path.exists()
        dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
        assert dashboard["ok"] is True
        assert dashboard["status_label"] == "Focused Suite Synced"
        assert dashboard["last_test_file"] == "src/tests/rpg/test_bundle_ab_focused_suite_registry_dashboard.py"
    finally:
        Path.write_text = original_write_text


def test_bundle_ab_injects_focused_suite_report_section_with_command_and_collapsed_raw_json(tmp_path):
    namespace = _load_bundle_ab_namespace()
    original_write_text = namespace["_BUNDLE_AB_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        (tmp_path / "one-thousand-turn-focused-suite-registry-summary.json").write_text(
            json.dumps(_registry_payload(True)),
            encoding="utf-8",
        )
        report_path = tmp_path / "autoplay-campaign-report.html"
        report_path.write_text(
            "<html><body><h1>Autoplay Campaign Report</h1><main><p>Body</p></main></body></html>",
            encoding="utf-8",
        )
        rendered = report_path.read_text(encoding="utf-8")

        assert 'id="bundle-ab-focused-suite-registry-dashboard"' in rendered
        assert "Focused Suite Registry" in rendered
        assert "Focused Suite Synced" in rendered
        assert "Canonical E-AB focused test command" in rendered
        assert "Canonical E-Z focused test command" not in rendered
        assert "python -m pytest" in rendered
        assert "src/tests/rpg/test_bundle_z_release_candidate_artifact_index_dashboard.py" in rendered
        assert "src/tests/rpg/test_bundle_ab_focused_suite_registry_dashboard.py" in rendered
        assert '<details class="bundle-ab-raw-details">' in rendered
        raw_start = rendered.index('<details class="bundle-ab-raw-details">')
        raw_open = rendered[raw_start : rendered.index(">", raw_start) + 1]
        assert " open" not in raw_open
        assert "<p>Body</p>" in rendered
    finally:
        Path.write_text = original_write_text
