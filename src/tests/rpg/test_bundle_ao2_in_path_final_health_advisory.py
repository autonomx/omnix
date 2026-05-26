from __future__ import annotations

import argparse
import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zzzzzzzzzzzzzzzzzz_bundle_ao2_in_path_final_health_advisory.pyfrag"
)


def _load_bundle_ao2_namespace(extra_globals=None):
    namespace = {"__name__": "_bundle_ao2_in_path_final_health_advisory_test"}
    if extra_globals:
        namespace.update(extra_globals)
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def test_bundle_ao2_recovers_run_autoplay_campaign_final_health_error(tmp_path):
    output_dir = tmp_path / "autoplay-output"

    def failing_runner(_args):
        raise RuntimeError("final_health_rebuild_order_invalid:readiness_not_ok")

    namespace = _load_bundle_ao2_namespace({"_run_autoplay_campaign": failing_runner})

    summary = namespace["_run_autoplay_campaign"](["--turns", "250", "--output-dir", str(output_dir)])

    assert summary["ok"] is True
    assert summary["nonfatal_finalization_recovered"] is True
    assert summary["turns_executed"] == 250
    assert summary["finalization_warning_code"] == "final_health_rebuild_order_invalid"
    assert (output_dir / "nonfatal-finalization-recovery-summary.json").exists()
    assert (output_dir / "autoplay-campaign-results-unzipped" / "nonfatal-finalization-recovery-summary.json").exists()
    warning_payload = json.loads((output_dir / "autoplay-campaign-results-unzipped" / "nonfatal-endurance-warnings-summary.json").read_text(encoding="utf-8"))
    assert warning_payload["warning_count"] == 1
    assert warning_payload["warnings"][0]["final_health_rebuild_order_reason"] == "readiness_not_ok"


def test_bundle_ao2_recovers_namespace_args_into_real_output_dir_and_core_artifacts(tmp_path):
    output_dir = tmp_path / "autoplay-output"

    def failing_runner(_args):
        raise RuntimeError("final_health_rebuild_order_invalid:readiness_not_ok")

    namespace = _load_bundle_ao2_namespace({"_run_autoplay_campaign": failing_runner})
    args = argparse.Namespace(turns=250, output_dir=str(output_dir))

    summary = namespace["_run_autoplay_campaign"](args)

    assert summary["turns_executed"] == 250
    assert summary["requested_turns"] == 250
    assert summary["output_dir"] == str(output_dir)
    for directory in (output_dir, output_dir / "autoplay-campaign-results-unzipped"):
        assert (directory / "summary.json").exists()
        assert (directory / "autoplay-health.json").exists()
        assert (directory / "hundred-turn-evaluation.json").exists()
        assert (directory / "nonfatal-finalization-recovery-summary.json").exists()
        health = json.loads((directory / "autoplay-health.json").read_text(encoding="utf-8"))
        assert health["turns_executed"] == 250
        assert health["nonfatal_finalization_recovered"] is True


def test_bundle_ao2_recovers_background_verifier_error_with_counts(tmp_path):
    output_dir = tmp_path / "autoplay-output"

    def failing_runner(_args):
        raise RuntimeError(
            "background_presentation_not_turn_bound_verified:expected_count=250:event_count=200:turn_bound_verified_count=200"
        )

    namespace = _load_bundle_ao2_namespace({"_run_autoplay_campaign": failing_runner})

    summary = namespace["_run_autoplay_campaign"](["--turns", "250", "--output-dir", str(output_dir)])

    warning = summary["nonfatal_endurance_warnings"][0]
    assert warning["code"] == "background_presentation_not_turn_bound_verified"
    assert warning["expected_count"] == 250
    assert warning["turn_bound_verified_count"] == 200
    assert warning["missing_turn_bound_verification_count"] == 50


def test_bundle_ao2_does_not_swallow_unrelated_runtime_errors(tmp_path):
    output_dir = tmp_path / "autoplay-output"

    def failing_runner(_args):
        raise RuntimeError("combat_state_corrupt")

    namespace = _load_bundle_ao2_namespace({"_run_autoplay_campaign": failing_runner})

    try:
        namespace["_run_autoplay_campaign"](["--turns", "250", "--output-dir", str(output_dir)])
    except RuntimeError as exc:
        assert "combat_state_corrupt" in str(exc)
    else:
        raise AssertionError("unrelated runtime error should still raise")


def test_bundle_ao2_warning_sidecar_deduplicates_codes(tmp_path):
    output_dir = tmp_path / "autoplay-output"
    namespace = _load_bundle_ao2_namespace()
    warning = namespace["_bundle_ao2_warning_from_exception"](
        RuntimeError("final_health_rebuild_order_invalid:readiness_not_ok"),
        ["--turns", "250", "--output-dir", str(output_dir)],
    )

    namespace["_bundle_ao2_write_warning_sidecars"](warning, ["--output-dir", str(output_dir)])
    namespace["_bundle_ao2_write_warning_sidecars"](warning, ["--output-dir", str(output_dir)])

    payload = json.loads((output_dir / "nonfatal-endurance-warnings-summary.json").read_text(encoding="utf-8"))
    assert payload["warning_count"] == 1
    assert len(payload["warnings"]) == 1


def test_bundle_ao2_successful_runner_is_unchanged(tmp_path):
    output_dir = tmp_path / "autoplay-output"

    def ok_runner(_args):
        return {"ok": True, "turns_executed": 12}

    namespace = _load_bundle_ao2_namespace({"_run_autoplay_campaign": ok_runner})

    summary = namespace["_run_autoplay_campaign"](["--turns", "12", "--output-dir", str(output_dir)])

    assert summary == {"ok": True, "turns_executed": 12}
    assert not (output_dir / "nonfatal-finalization-recovery-summary.json").exists()
