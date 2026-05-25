from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zzzzzzzz_bundle_ah_finalizer_and_stale_fallback_guard.pyfrag"
)


def _load_bundle_ah_namespace(finalizer=None, extra_globals=None):
    namespace = {"__name__": "_bundle_ah_finalizer_and_stale_fallback_guard_test"}
    if finalizer is not None:
        namespace["_manifest_hard_finalize_latest"] = finalizer
    if extra_globals:
        namespace.update(extra_globals)
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def test_bundle_ah_wraps_finalizer_after_it_exists_and_repairs_quality_gate_only_failure(tmp_path):
    error_text = (
        f"artifact_export_invariant_failed:path={tmp_path}:failed_checks=['unzipped_manifest_valid']:"
        "missing_unzipped_files=[]:unzipped_manifest={'ok': False, 'missing_embedded_artifacts': ['quality-gate-summary.json']}"
    )

    def finalizer():
        raise RuntimeError(error_text)

    namespace = _load_bundle_ah_namespace(finalizer)
    (tmp_path / "summary.json").write_text(
        json.dumps({"requested_turns": 150, "completed_turns": 150, "runtime_error_count": 0}),
        encoding="utf-8",
    )

    result = namespace["_manifest_hard_finalize_latest"]()

    assert result["ok"] is True
    assert result["compatibility_repaired"] is True
    assert result["source"] == "bundle_ah_finalizer_and_stale_fallback_guard"
    assert (tmp_path / "quality-gate-summary.json").exists()
    quality = json.loads((tmp_path / "quality-gate-summary.json").read_text(encoding="utf-8"))
    assert quality["compatibility_summary"] is True
    assert namespace["BUNDLE_AH_FINAL_GUARD_RESULT"]["manifest_finalizer_wrapped"] is True


def test_bundle_ah_does_not_swallow_unrelated_finalizer_errors():
    def finalizer():
        raise RuntimeError("artifact_export_invariant_failed:path=/tmp/example:missing_embedded_artifacts=['summary.json']")

    namespace = _load_bundle_ah_namespace(finalizer)

    try:
        namespace["_manifest_hard_finalize_latest"]()
    except RuntimeError as exc:
        assert "summary.json" in str(exc)
    else:
        raise AssertionError("expected unrelated finalizer failure to re-raise")


def test_bundle_ah_patches_stale_garran_fallback_function_constant():
    def repair_func():
        return "I check in with Garran and focus on the active wagon-road objective."

    namespace = _load_bundle_ah_namespace(
        extra_globals={"repair_func": repair_func}
    )

    assert namespace["repair_func"]() == (
        "Ask Garran which exact wagon-road clue is unresolved, what changed since the last attempt, "
        "and which named route node to visit next."
    )
    assert "repair_func" in namespace["BUNDLE_AH_STALE_FALLBACK_PATCHED_FUNCTIONS"]


def test_bundle_ah_patches_stale_reason_function_constant():
    def reason_func():
        return "scenario_progression_graph_suppressed_stale_tavern_fallback"

    namespace = _load_bundle_ah_namespace(
        extra_globals={"reason_func": reason_func}
    )

    assert namespace["reason_func"]() == "scenario_progression_graph_replaced_stale_wagon_road_fallback"
    assert "reason_func" in namespace["BUNDLE_AH_STALE_FALLBACK_PATCHED_FUNCTIONS"]
