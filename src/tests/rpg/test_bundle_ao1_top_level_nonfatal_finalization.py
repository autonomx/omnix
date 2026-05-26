from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zzzzzzzzzzzzzzzzz_bundle_ao1_top_level_nonfatal_finalization.pyfrag"
)


def _load_bundle_ao1_namespace(extra_globals=None):
    namespace = {"__name__": "_bundle_ao1_top_level_nonfatal_finalization_test"}
    if extra_globals:
        namespace.update(extra_globals)
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def test_bundle_ao1_identifies_known_final_health_error():
    namespace = _load_bundle_ao1_namespace()
    exc = RuntimeError("final_health_rebuild_order_invalid:readiness_not_ok")

    warning = namespace["_bundle_ao1_warning_from_exception"](exc)

    assert warning["code"] == "final_health_rebuild_order_invalid"
    assert warning["final_health_rebuild_order_warning"] is True
    assert warning["final_health_rebuild_order_reason"] == "readiness_not_ok"
    assert warning["advisory_only"] is True


def test_bundle_ao1_writes_warning_sidecars_from_output_dir(tmp_path):
    namespace = _load_bundle_ao1_namespace()
    output_dir = tmp_path / "autoplay-output"
    unzipped = output_dir / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)
    warning = namespace["_bundle_ao1_warning_from_exception"](
        RuntimeError("final_health_rebuild_order_invalid:readiness_not_ok")
    )

    result = namespace["_bundle_ao1_write_warning_sidecars"](
        warning,
        ["--output-dir", str(output_dir)],
    )

    assert result["ok"] is True
    for directory in (output_dir, unzipped):
        path = directory / "nonfatal-endurance-warnings-summary.json"
        assert path.exists()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["warning_count"] == 1
        assert payload["warnings"][0]["code"] == "final_health_rebuild_order_invalid"


def test_bundle_ao1_main_wrapper_returns_zero_for_known_postrun_finalization_error(tmp_path):
    output_dir = tmp_path / "autoplay-output"
    (output_dir / "autoplay-campaign-results-unzipped").mkdir(parents=True)

    def failing_main(_argv=None):
        raise RuntimeError("final_health_rebuild_order_invalid:readiness_not_ok")

    namespace = _load_bundle_ao1_namespace({"main": failing_main})

    exit_code = namespace["main"](["--output-dir", str(output_dir)])

    assert exit_code == 0
    assert namespace["BUNDLE_AO1_LAST_NONFATAL_FINALIZATION_WARNING"]["code"] == "final_health_rebuild_order_invalid"
    assert (output_dir / "autoplay-campaign-results-unzipped" / "nonfatal-endurance-warnings-summary.json").exists()


def test_bundle_ao1_main_wrapper_does_not_swallow_unrelated_errors(tmp_path):
    output_dir = tmp_path / "autoplay-output"
    output_dir.mkdir()

    def failing_main(_argv=None):
        raise RuntimeError("combat_state_corrupt")

    namespace = _load_bundle_ao1_namespace({"main": failing_main})

    try:
        namespace["main"](["--output-dir", str(output_dir)])
    except RuntimeError as exc:
        assert "combat_state_corrupt" in str(exc)
    else:
        raise AssertionError("unrelated runtime error should still raise")


def test_bundle_ao1_deduplicates_warning_sidecar_codes(tmp_path):
    namespace = _load_bundle_ao1_namespace()
    output_dir = tmp_path / "autoplay-output"
    (output_dir / "autoplay-campaign-results-unzipped").mkdir(parents=True)
    warning = namespace["_bundle_ao1_warning_from_exception"](
        RuntimeError("final_health_rebuild_order_invalid:readiness_not_ok")
    )

    namespace["_bundle_ao1_write_warning_sidecars"](warning, ["--output-dir", str(output_dir)])
    namespace["_bundle_ao1_write_warning_sidecars"](warning, ["--output-dir", str(output_dir)])

    payload = json.loads((output_dir / "nonfatal-endurance-warnings-summary.json").read_text(encoding="utf-8"))
    assert payload["warning_count"] == 1
    assert len(payload["warnings"]) == 1
