from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zz_bundle_s_live_1000_run_profile.pyfrag"
)


def _load_bundle_s_namespace():
    namespace = {"__name__": "_bundle_s_live_1000_run_profile_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _promoted_preflight_result():
    return {
        "ok": True,
        "promote_to_live_1000_turn_run": True,
        "recommended_next_step": "promote_to_live_1000_turn_run",
    }


def _blocked_preflight_result():
    return {
        "ok": False,
        "promote_to_live_1000_turn_run": False,
        "advisory_failures": ["blocking_turn_p95_within_budget"],
        "recommended_next_step": "fix_preflight_result_failures_before_live_1000_turn_run",
    }


def test_bundle_s_profile_descriptor_and_live_command_are_explicit():
    namespace = _load_bundle_s_namespace()
    profile = namespace["_BUNDLE_S_PROFILE"]
    command = namespace["_bundle_s_build_live_command"]()

    assert profile["format_version"] == "bundle_s_live_1000_turn_profile_v1"
    assert profile["name"] == "live_1000"
    assert profile["target_turns"] == 1000
    assert profile["requires_preflight_promotion"] is True
    assert profile["defaults"]["turns"] == 1000
    assert profile["defaults"]["narration_mode"] == "deferred"
    assert profile["defaults"]["background_llm_mode"] == "combined"
    assert profile["defaults"]["compact_transcript_mode"] is True
    assert profile["defaults"]["transcript_detail"] == "auto"
    assert profile["defaults"]["zip_artifacts_required"] is True
    assert command[:2] == ["python", "src/tests/rpg/autoplay_llm_campaign.py"]
    assert namespace["_bundle_s_missing_command_flags"](command) == []
    assert "--turns" in command
    assert "1000" in command
    assert "--transcript-detail" in command
    assert "auto" in command
    assert "--capture-console-log" in command
    assert "--compact-transcript-mode" not in command
    assert "--zip-results" not in command


def test_bundle_s_profile_arg_expansion_preserves_caller_flags():
    namespace = _load_bundle_s_namespace()
    stripped, applied = namespace["_bundle_s_strip_profile_args"](
        ["--live-profile", "live_1000", "--turns", "777", "--artifact-detail", "compact"]
    )
    expanded = namespace["_bundle_s_append_missing_profile_args"](stripped)

    assert applied is True
    assert "--live-profile" not in expanded
    turns_index = expanded.index("--turns")
    artifact_index = expanded.index("--artifact-detail")
    transcript_index = expanded.index("--transcript-detail")
    assert expanded[turns_index + 1] == "777"
    assert expanded[artifact_index + 1] == "compact"
    assert expanded[transcript_index + 1] == "auto"
    assert "--narration-mode" in expanded
    assert "deferred" in expanded
    assert "--background-llm-mode" in expanded
    assert "combined" in expanded
    assert "--capture-console-log" in expanded
    assert "--compact-transcript-mode" not in expanded
    assert "--zip-results" not in expanded


def test_bundle_s_live_profile_passes_only_with_promoted_preflight(tmp_path):
    namespace = _load_bundle_s_namespace()
    (tmp_path / "one-thousand-turn-preflight-result-summary.json").write_text(
        json.dumps(_promoted_preflight_result()),
        encoding="utf-8",
    )

    result = namespace["_bundle_s_evaluate_live_run_profile"](tmp_path)

    assert result["format_version"] == "bundle_s_live_1000_turn_profile_summary_v1"
    assert result["source"] == "bundle_s_live_1000_run_profile"
    assert result["ok"] is True
    assert result["ready_to_start_live_1000_turn_run"] is True
    assert result["checks"]["preflight_result_present"] is True
    assert result["checks"]["preflight_result_ok"] is True
    assert result["checks"]["preflight_promoted_live_run"] is True
    assert result["checks"]["promotion_guard_required"] is True
    assert "--compact-transcript-mode" not in result["canonical_command"]
    assert "--zip-results" not in result["canonical_command"]
    assert result["recommended_next_step"] == "run_live_1000_command"


def test_bundle_s_live_profile_blocks_without_or_with_failed_preflight(tmp_path):
    namespace = _load_bundle_s_namespace()

    missing = namespace["_bundle_s_evaluate_live_run_profile"](tmp_path)
    assert missing["ok"] is False
    assert "preflight_result_present" in missing["advisory_failures"]
    assert "preflight_result_ok" in missing["advisory_failures"]
    assert "preflight_promoted_live_run" in missing["advisory_failures"]

    (tmp_path / "one-thousand-turn-preflight-result-summary.json").write_text(
        json.dumps(_blocked_preflight_result()),
        encoding="utf-8",
    )
    blocked = namespace["_bundle_s_evaluate_live_run_profile"](tmp_path)
    assert blocked["ok"] is False
    assert blocked["ready_to_start_live_1000_turn_run"] is False
    assert "preflight_result_ok" in blocked["advisory_failures"]
    assert "preflight_promoted_live_run" in blocked["advisory_failures"]
    assert blocked["recommended_next_step"] == "run_or_fix_preflight_1000_before_live_1000"


def test_bundle_s_writes_summary_when_preflight_result_is_exported(tmp_path):
    namespace = _load_bundle_s_namespace()
    original_write_text = namespace["_BUNDLE_S_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        (tmp_path / "one-thousand-turn-preflight-result-summary.json").write_text(
            json.dumps(_promoted_preflight_result()),
            encoding="utf-8",
        )

        summary_path = tmp_path / "one-thousand-turn-live-run-profile-summary.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["ok"] is True
        assert summary["ready_to_start_live_1000_turn_run"] is True
        assert summary["checks"]["preflight_promoted_live_run"] is True
        assert "--compact-transcript-mode" not in summary["canonical_command"]
        assert "--zip-results" not in summary["canonical_command"]
        assert summary["recommended_next_step"] == "run_live_1000_command"
    finally:
        Path.write_text = original_write_text
