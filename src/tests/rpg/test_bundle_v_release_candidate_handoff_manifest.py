from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zz_bundle_v_release_candidate_handoff_manifest.pyfrag"
)


def _load_bundle_v_namespace():
    namespace = {"__name__": "_bundle_v_release_candidate_handoff_manifest_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _write_required_artifacts(tmp_path: Path, namespace):
    payloads = {
        "one-thousand-turn-release-candidate-dashboard-summary.json": {
            "ok": True,
            "status_label": "Release Candidate Ready",
            "release_candidate_ready": True,
        },
        "one-thousand-turn-live-result-summary.json": {
            "ok": True,
            "release_candidate_ready": True,
        },
    }
    for file_name in namespace["_BUNDLE_V_REQUIRED_FILES"]:
        payload = payloads.get(file_name, {"ok": True, "source": file_name})
        (tmp_path / file_name).write_text(json.dumps(payload), encoding="utf-8")


def test_bundle_v_command_catalog_is_explicit():
    namespace = _load_bundle_v_namespace()
    commands = namespace["_BUNDLE_V_COMMANDS"]

    assert set(commands) == {"focused_test_suite", "preflight_1000", "live_1000"}
    assert commands["preflight_1000"] == [
        "python",
        "src/tests/rpg/autoplay_llm_campaign.py",
        "--preflight-profile",
        "preflight_1000",
    ]
    assert commands["live_1000"] == [
        "python",
        "src/tests/rpg/autoplay_llm_campaign.py",
        "--live-profile",
        "live_1000",
    ]
    focused = commands["focused_test_suite"]
    assert "src/tests/rpg/test_bundle_v_release_candidate_handoff_manifest.py" in focused
    assert "src/tests/rpg/test_bundle_w_release_candidate_handoff_dashboard.py" in focused
    assert "src/tests/rpg/test_bundle_x_release_candidate_runbook.py" in focused
    assert "src/tests/rpg/test_bundle_y_release_candidate_artifact_index.py" in focused
    assert "src/tests/rpg/test_bundle_z_release_candidate_artifact_index_dashboard.py" in focused
    assert "src/tests/rpg/test_bundle_ab_focused_suite_registry_dashboard.py" in focused
    assert focused[-1] == "src/tests/rpg/test_bundle_ab_focused_suite_registry_dashboard.py"
    assert namespace["_bundle_v_command_text"](["python", "-m", "pytest"]) == "python -m pytest"


def test_bundle_v_artifact_checklist_passes_when_required_files_exist(tmp_path):
    namespace = _load_bundle_v_namespace()
    _write_required_artifacts(tmp_path, namespace)
    (tmp_path / "autoplay-campaign-report.html").write_text("<html>report</html>", encoding="utf-8")
    (tmp_path / "autoplay-campaign-results.zip").write_bytes(b"PK\x03\x04fake")

    checklist = namespace["_bundle_v_build_artifact_checklist"](tmp_path)

    assert checklist["required_file_count"] == len(namespace["_BUNDLE_V_REQUIRED_FILES"])
    assert checklist["present_required_file_count"] == len(namespace["_BUNDLE_V_REQUIRED_FILES"])
    assert checklist["missing_required"] == []
    optional = {entry["file"]: entry for entry in checklist["optional_product"]}
    assert optional["autoplay-campaign-report.html"]["present"] is True
    assert optional["autoplay-campaign-results.zip"]["present"] is True


def test_bundle_v_handoff_manifest_ready_when_dashboard_live_result_and_artifacts_pass(tmp_path):
    namespace = _load_bundle_v_namespace()
    _write_required_artifacts(tmp_path, namespace)

    result = namespace["_bundle_v_evaluate_release_candidate_handoff"](tmp_path)

    assert result["format_version"] == "bundle_v_release_candidate_handoff_manifest_v1"
    assert result["source"] == "bundle_v_release_candidate_handoff_manifest"
    assert result["ok"] is True
    assert result["advisory_only"] is True
    assert result["release_candidate_handoff_ready"] is True
    assert result["advisory_failures"] == []
    assert result["checks"]["release_candidate_dashboard_ready"] is True
    assert result["checks"]["live_result_release_candidate_ready"] is True
    assert result["checks"]["required_handoff_artifacts_present"] is True
    assert result["checks"]["focused_test_command_present"] is True
    assert result["checks"]["preflight_command_present"] is True
    assert result["checks"]["live_command_present"] is True
    assert result["metrics"]["missing_required_file_count"] == 0
    assert result["recommended_next_step"] == "archive_release_candidate_artifacts"


def test_bundle_v_handoff_manifest_reports_missing_and_blocked_artifacts(tmp_path):
    namespace = _load_bundle_v_namespace()
    (tmp_path / "one-thousand-turn-release-candidate-dashboard-summary.json").write_text(
        json.dumps({"ok": False, "status_label": "Release Candidate Blocked"}),
        encoding="utf-8",
    )
    (tmp_path / "one-thousand-turn-live-result-summary.json").write_text(
        json.dumps({"ok": False, "release_candidate_ready": False}),
        encoding="utf-8",
    )

    result = namespace["_bundle_v_evaluate_release_candidate_handoff"](tmp_path)

    assert result["ok"] is False
    assert result["release_candidate_handoff_ready"] is False
    assert "release_candidate_dashboard_ready" in result["advisory_failures"]
    assert "live_result_release_candidate_ready" in result["advisory_failures"]
    assert "required_handoff_artifacts_present" in result["advisory_failures"]
    assert result["metrics"]["missing_required_file_count"] > 0
    assert result["recommended_next_step"] == "complete_release_candidate_handoff_artifacts"


def test_bundle_v_writes_manifest_when_required_artifacts_are_exported(tmp_path):
    namespace = _load_bundle_v_namespace()
    original_write_text = namespace["_BUNDLE_V_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        _write_required_artifacts(tmp_path, namespace)

        manifest_path = tmp_path / "one-thousand-turn-release-candidate-handoff-manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["ok"] is True
        assert manifest["release_candidate_handoff_ready"] is True
        assert manifest["checks"]["required_handoff_artifacts_present"] is True
        assert manifest["commands"]["preflight_1000"]["text"] == "python src/tests/rpg/autoplay_llm_campaign.py --preflight-profile preflight_1000"
        assert manifest["commands"]["focused_test_suite"]["argv"][-1] == "src/tests/rpg/test_bundle_ab_focused_suite_registry_dashboard.py"
    finally:
        Path.write_text = original_write_text
