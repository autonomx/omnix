from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zz_bundle_aa_focused_suite_registry.pyfrag"
)


def _load_bundle_aa_namespace():
    namespace = {"__name__": "_bundle_aa_focused_suite_registry_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _handoff_payload(namespace):
    command = namespace["_bundle_aa_build_focused_command"]()
    return {
        "ok": True,
        "commands": {
            "focused_test_suite": {"argv": command, "text": namespace["_bundle_aa_command_text"](command)},
            "preflight_1000": {"argv": ["python", "src/tests/rpg/autoplay_llm_campaign.py", "--preflight-profile", "preflight_1000"]},
            "live_1000": {"argv": ["python", "src/tests/rpg/autoplay_llm_campaign.py", "--live-profile", "live_1000"]},
        },
    }


def test_bundle_aa_registry_lists_full_e_through_ab_suite_in_order():
    namespace = _load_bundle_aa_namespace()
    test_files = namespace["_BUNDLE_AA_TEST_FILES"]
    command = namespace["_bundle_aa_build_focused_command"]()

    assert len(test_files) == 23
    assert test_files[0] == "src/tests/rpg/test_bundle_e_product_report_rendering.py"
    assert test_files[-1] == "src/tests/rpg/test_bundle_ab_focused_suite_registry_dashboard.py"
    assert command[:3] == ["python", "-m", "pytest"]
    assert command[3:] == test_files
    assert namespace["_bundle_aa_duplicate_test_files"]() == []


def test_bundle_aa_registry_passes_when_handoff_command_matches(tmp_path):
    namespace = _load_bundle_aa_namespace()
    (tmp_path / "one-thousand-turn-release-candidate-handoff-manifest.json").write_text(
        json.dumps(_handoff_payload(namespace)),
        encoding="utf-8",
    )

    result = namespace["_bundle_aa_evaluate_focused_suite_registry"](_repo_root(), tmp_path)

    assert result["format_version"] == "bundle_aa_focused_suite_registry_summary_v1"
    assert result["source"] == "bundle_aa_focused_suite_registry"
    assert result["ok"] is True
    assert result["focused_suite_registry_ready"] is True
    assert result["advisory_failures"] == []
    assert result["checks"]["registry_has_expected_range"] is True
    assert result["checks"]["registry_test_count_expected"] is True
    assert result["checks"]["registry_has_no_duplicates"] is True
    assert result["checks"]["registry_files_exist"] is True
    assert result["checks"]["command_starts_with_pytest"] is True
    assert result["checks"]["handoff_command_matches_registry"] is True
    assert result["canonical_command"]["argv"][-1] == "src/tests/rpg/test_bundle_ab_focused_suite_registry_dashboard.py"
    assert result["recommended_next_step"] == "use_canonical_e_ab_focused_suite_command"


def test_bundle_aa_registry_reports_handoff_command_drift(tmp_path):
    namespace = _load_bundle_aa_namespace()
    drifted = _handoff_payload(namespace)
    drifted["commands"]["focused_test_suite"]["argv"] = ["python", "-m", "pytest", "src/tests/rpg/test_bundle_v_release_candidate_handoff_manifest.py"]
    (tmp_path / "one-thousand-turn-release-candidate-handoff-manifest.json").write_text(
        json.dumps(drifted),
        encoding="utf-8",
    )

    result = namespace["_bundle_aa_evaluate_focused_suite_registry"](_repo_root(), tmp_path)

    assert result["ok"] is False
    assert result["focused_suite_registry_ready"] is False
    assert "handoff_command_matches_registry" in result["advisory_failures"]
    assert result["recommended_next_step"] == "fix_focused_suite_registry_drift"


def test_bundle_aa_writes_summary_when_handoff_manifest_is_exported(tmp_path):
    namespace = _load_bundle_aa_namespace()
    original_write_text = namespace["_BUNDLE_AA_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        # Put the temp output under the real repo tree so the registry can locate src/tests/rpg.
        output_dir = _repo_root() / "resources" / "data" / "test-results" / "bundle_aa_registry_test"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "one-thousand-turn-release-candidate-handoff-manifest.json").write_text(
            json.dumps(_handoff_payload(namespace)),
            encoding="utf-8",
        )

        summary_path = output_dir / "one-thousand-turn-focused-suite-registry-summary.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["ok"] is True
        assert summary["focused_suite_registry_ready"] is True
        assert summary["metrics"]["test_file_count"] == 23
        assert summary["canonical_command"]["argv"][-1] == "src/tests/rpg/test_bundle_ab_focused_suite_registry_dashboard.py"
    finally:
        Path.write_text = original_write_text
