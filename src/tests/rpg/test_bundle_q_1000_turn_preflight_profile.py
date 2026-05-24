from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zz_bundle_q_1000_turn_preflight_profile.pyfrag"
)


def _load_bundle_q_namespace():
    namespace = {"__name__": "_bundle_q_1000_turn_preflight_profile_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _aggregator_payload():
    return {
        "ok": True,
        "ready_for_1000_turn_preflight": True,
        "ready_for_live_1000_turn_run": False,
        "required_gate_count": 9,
        "passing_required_gate_count": 9,
    }


def _dashboard_payload():
    return {
        "ok": True,
        "status_label": "Preflight Ready",
        "status_class": "warn",
        "ready_for_1000_turn_preflight": True,
        "required_gate_count": 9,
        "passing_required_gate_count": 9,
    }


def test_bundle_q_profile_descriptor_and_command_are_explicit():
    namespace = _load_bundle_q_namespace()
    profile = namespace["_BUNDLE_Q_PROFILE"]
    command = namespace["_bundle_q_build_preflight_command"]()

    assert profile["format_version"] == "bundle_q_1000_turn_preflight_profile_v1"
    assert profile["name"] == "preflight_1000"
    assert profile["target_turns"] == 1000
    assert profile["defaults"]["turns"] == 1000
    assert profile["defaults"]["narration_mode"] == "deferred"
    assert profile["defaults"]["background_llm_mode"] == "combined"
    assert profile["defaults"]["compact_transcript_mode"] is True
    assert command[:2] == ["python", "src/tests/rpg/autoplay_llm_campaign.py"]
    assert namespace["_bundle_q_missing_command_flags"](command) == []
    assert "--turns" in command
    assert "1000" in command
    assert "--compact-transcript-mode" in command


def test_bundle_q_profile_arg_expansion_preserves_caller_flags():
    namespace = _load_bundle_q_namespace()
    stripped, applied = namespace["_bundle_q_strip_profile_args"](
        ["--preflight-profile", "preflight_1000", "--turns", "777", "--artifact-detail", "compact"]
    )
    expanded = namespace["_bundle_q_append_missing_profile_args"](stripped)

    assert applied is True
    assert "--preflight-profile" not in expanded
    turns_index = expanded.index("--turns")
    artifact_index = expanded.index("--artifact-detail")
    assert expanded[turns_index + 1] == "777"
    assert expanded[artifact_index + 1] == "compact"
    assert "--narration-mode" in expanded
    assert "deferred" in expanded
    assert "--background-llm-mode" in expanded
    assert "combined" in expanded
    assert "--compact-transcript-mode" in expanded


def test_bundle_q_preflight_profile_passes_with_ready_aggregator_and_dashboard(tmp_path):
    namespace = _load_bundle_q_namespace()
    (tmp_path / "one-thousand-turn-readiness-aggregator-summary.json").write_text(
        json.dumps(_aggregator_payload()),
        encoding="utf-8",
    )
    (tmp_path / "one-thousand-turn-readiness-dashboard-summary.json").write_text(
        json.dumps(_dashboard_payload()),
        encoding="utf-8",
    )

    result = namespace["_bundle_q_evaluate_preflight_profile"](tmp_path)

    assert result["format_version"] == "bundle_q_1000_turn_preflight_profile_summary_v1"
    assert result["source"] == "bundle_q_1000_turn_preflight_profile"
    assert result["ok"] is True
    assert result["advisory_only"] is True
    assert result["advisory_failures"] == []
    assert result["checks"]["profile_descriptor_present"] is True
    assert result["checks"]["target_turns_1000"] is True
    assert result["checks"]["canonical_command_complete"] is True
    assert result["checks"]["aggregator_preflight_ready"] is True
    assert result["checks"]["dashboard_present"] is True
    assert result["checks"]["dashboard_preflight_ready"] is True
    assert result["recommended_next_step"] == "run_preflight_1000_command"


def test_bundle_q_preflight_profile_reports_missing_dashboard_and_aggregator(tmp_path):
    namespace = _load_bundle_q_namespace()
    result = namespace["_bundle_q_evaluate_preflight_profile"](tmp_path)

    assert result["ok"] is False
    assert "aggregator_preflight_ready" in result["advisory_failures"]
    assert "dashboard_present" in result["advisory_failures"]
    assert "dashboard_preflight_ready" in result["advisory_failures"]
    assert result["recommended_next_step"] == "fix_readiness_dashboard_before_preflight_1000"


def test_bundle_q_writes_summary_when_dashboard_or_aggregator_is_exported(tmp_path):
    namespace = _load_bundle_q_namespace()
    original_write_text = namespace["_BUNDLE_Q_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        (tmp_path / "one-thousand-turn-readiness-aggregator-summary.json").write_text(
            json.dumps(_aggregator_payload()),
            encoding="utf-8",
        )
        (tmp_path / "one-thousand-turn-readiness-dashboard-summary.json").write_text(
            json.dumps(_dashboard_payload()),
            encoding="utf-8",
        )

        summary_path = tmp_path / "one-thousand-turn-preflight-profile-summary.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["ok"] is True
        assert summary["checks"]["target_turns_1000"] is True
        assert summary["checks"]["canonical_command_complete"] is True
        assert summary["recommended_next_step"] == "run_preflight_1000_command"
    finally:
        Path.write_text = original_write_text
