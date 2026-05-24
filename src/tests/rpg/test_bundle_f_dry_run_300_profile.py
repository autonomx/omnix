from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zz_bundle_f_dry_run_300_profile.pyfrag"
)


def _load_bundle_f_namespace():
    namespace = {"__name__": "_bundle_f_dry_run_300_profile_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _passing_artifacts():
    return {
        "artifact-manifest-digest.json": {
            "ok": True,
            "manifest_ok": True,
            "manifest_exists": True,
            "invariant_ok": True,
            "zip_manifest_valid_count": 1,
        },
        "content-exhaustion-forecast-summary.json": {
            "ok": True,
            "content_exhaustion_estimate": 325,
        },
        "transcript-payload-budget-summary.json": {
            "ok": True,
            "turn_count": 100,
            "total_bytes": 1_000_000,
            "budget_ok": True,
        },
        "long-run-dry-run-projection-summary.json": {
            "ok": True,
            "projected_state_bytes": 2_000_000,
            "projected_transcript_bytes": 3_000_000,
        },
        "summary.json": {
            "runtime_error_count": 0,
            "unresolved_final_background_jobs": 0,
        },
    }


def test_bundle_f_dry_run_300_profile_descriptor_is_explicit():
    namespace = _load_bundle_f_namespace()
    profile = namespace["_BUNDLE_F_DRY_RUN_300_PROFILE"]

    assert profile["name"] == "dry_run_300"
    assert profile["target_turns"] == 300
    assert profile["defaults"]["turns"] == 300
    assert profile["defaults"]["narration_mode"] == "deferred"
    assert profile["defaults"]["background_llm_mode"] == "combined"
    assert profile["defaults"]["checkpoint_interval"] == 25
    assert profile["defaults"]["artifact_detail"] == "full"
    assert profile["defaults"]["compact_transcript_mode"] is True
    assert "--turns" in profile["canonical_cli_args"]
    assert "300" in profile["canonical_cli_args"]


def test_bundle_f_endurance_gate_passes_when_300_turn_requirements_are_met():
    namespace = _load_bundle_f_namespace()
    result = namespace["_bundle_f_evaluate_300_turn_endurance"](_passing_artifacts())

    assert result["format_version"] == "bundle_f_dry_run_300_endurance_gate_v1"
    assert result["profile"] == "dry_run_300"
    assert result["target_turns"] == 300
    assert result["advisory_only"] is True
    assert result["ok"] is True
    assert result["advisory_failures"] == []
    assert result["checks"]["transcript_payload_bounded"] is True
    assert result["checks"]["state_size_bounded"] is True
    assert result["checks"]["content_exhaustion_supports_300"] is True
    assert result["checks"]["artifact_manifest_digest_ok"] is True
    assert result["checks"]["no_runtime_errors"] is True
    assert result["checks"]["no_unresolved_final_background_jobs"] is True
    assert result["recommended_next_run"] == "dry_run_300"


def test_bundle_f_endurance_gate_reports_advisory_failures_without_raising():
    namespace = _load_bundle_f_namespace()
    artifacts = _passing_artifacts()
    artifacts["content-exhaustion-forecast-summary.json"]["content_exhaustion_estimate"] = 200
    artifacts["artifact-manifest-digest.json"]["invariant_ok"] = False
    artifacts["summary.json"]["runtime_error_count"] = 1
    artifacts["summary.json"]["unresolved_final_background_jobs"] = 2
    artifacts["long-run-dry-run-projection-summary.json"]["projected_state_bytes"] = 99_000_000
    artifacts["long-run-dry-run-projection-summary.json"]["projected_transcript_bytes"] = 99_000_000

    result = namespace["_bundle_f_evaluate_300_turn_endurance"](artifacts)

    assert result["ok"] is False
    assert result["advisory_only"] is True
    assert set(result["advisory_failures"]) == {
        "transcript_payload_bounded",
        "state_size_bounded",
        "content_exhaustion_supports_300",
        "artifact_manifest_digest_ok",
        "no_runtime_errors",
        "no_unresolved_final_background_jobs",
    }
    assert result["recommended_next_run"] == "fix_advisory_failures_before_dry_run_300"


def test_bundle_f_writes_gate_summary_when_relevant_artifacts_are_exported(tmp_path):
    namespace = _load_bundle_f_namespace()
    original_write_text = namespace["_BUNDLE_F_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        for file_name, payload in _passing_artifacts().items():
            (tmp_path / file_name).write_text(json.dumps(payload), encoding="utf-8")

        gate_path = tmp_path / "dry-run-300-endurance-gate-summary.json"
        assert gate_path.exists()
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        assert gate["profile"] == "dry_run_300"
        assert gate["ok"] is True
        assert gate["checks"]["content_exhaustion_supports_300"] is True
    finally:
        Path.write_text = original_write_text


def test_bundle_f_profile_arg_expansion_keeps_existing_caller_flags():
    namespace = _load_bundle_f_namespace()
    stripped, applied = namespace["_bundle_f_strip_profile_args"](
        ["--profile", "dry_run_300", "--turns", "123", "--artifact-detail", "compact"]
    )
    expanded = namespace["_bundle_f_append_missing_profile_args"](stripped)

    assert applied is True
    assert "--profile" not in expanded
    turns_index = expanded.index("--turns")
    artifact_index = expanded.index("--artifact-detail")
    assert expanded[turns_index + 1] == "123"
    assert expanded[artifact_index + 1] == "compact"
    assert "--narration-mode" in expanded
    assert "deferred" in expanded
    assert "--checkpoint-interval" in expanded
    assert "25" in expanded
