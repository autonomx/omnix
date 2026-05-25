from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zzzzzz_bundle_ag_manifest_finalizer_quality_gate_tolerance.pyfrag"
)


def _load_bundle_ag_namespace_with_finalizer(finalizer=None):
    namespace = {"__name__": "_bundle_ag_manifest_finalizer_quality_gate_tolerance_test"}
    if finalizer is not None:
        namespace["_manifest_hard_finalize_latest"] = finalizer
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def test_bundle_ag_builds_min_quality_gate_summary(tmp_path):
    namespace = _load_bundle_ag_namespace_with_finalizer()
    (tmp_path / "summary.json").write_text(
        json.dumps({"requested_turns": 150, "completed_turns": 150, "runtime_error_count": 0}),
        encoding="utf-8",
    )

    payload = namespace["_bundle_ag_build_min_quality_gate"](tmp_path)

    assert payload["format_version"] in {"bundle_ag_quality_gate_summary_compat_v1", "bundle_af_quality_gate_summary_compat_v1"}
    assert payload["ok"] is True
    assert payload["compatibility_summary"] is True
    assert payload["metrics"]["requested_turns"] == 150
    assert payload["metrics"]["completed_turns"] == 150


def test_bundle_ag_repairs_quality_gate_only_finalizer_failure(tmp_path):
    error_text = (
        f"artifact_export_invariant_failed:path={tmp_path}:failed_checks=['unzipped_manifest_valid']:"
        "missing_unzipped_files=[]:unzipped_manifest={'ok': False, 'missing_embedded_artifacts': ['quality-gate-summary.json']}"
    )

    def finalizer():
        raise RuntimeError(error_text)

    namespace = _load_bundle_ag_namespace_with_finalizer(finalizer)
    (tmp_path / "summary.json").write_text(
        json.dumps({"requested_turns": 150, "completed_turns": 150, "runtime_error_count": 0}),
        encoding="utf-8",
    )

    result = namespace["_manifest_hard_finalize_latest"]()

    assert result["ok"] is True
    assert result["compatibility_repaired"] is True
    assert str(tmp_path.resolve()) in result["repaired_dirs"] or str(tmp_path) in result["repaired_dirs"]
    quality = json.loads((tmp_path / "quality-gate-summary.json").read_text(encoding="utf-8"))
    assert quality["compatibility_summary"] is True


def test_bundle_ag_does_not_swallow_unrelated_manifest_failures():
    def finalizer():
        raise RuntimeError("artifact_export_invariant_failed:path=/tmp/example:missing_embedded_artifacts=['summary.json']")

    namespace = _load_bundle_ag_namespace_with_finalizer(finalizer)

    try:
        namespace["_manifest_hard_finalize_latest"]()
    except RuntimeError as exc:
        assert "summary.json" in str(exc)
    else:
        raise AssertionError("expected unrelated manifest failure to re-raise")


def test_bundle_ag_patch_manifest_payload_removes_quality_gate_missing_artifact():
    namespace = _load_bundle_ag_namespace_with_finalizer()
    payload = {
        "ok": False,
        "checks": {
            "manifest_non_empty_json": True,
            "manifest_ok_true": False,
            "manifest_hard_finalized_true": True,
            "manifest_embedded_artifacts_non_empty": True,
            "manifest_required_embedded_present": False,
        },
        "missing_embedded_artifacts": ["quality-gate-summary.json"],
    }

    patched = namespace["_bundle_ag_patch_manifest_payload"](payload)

    assert patched["missing_embedded_artifacts"] == []
    assert patched["checks"]["manifest_required_embedded_present"] is True
    assert "added_quality_gate_summary" in patched["compatibility_repairs"]
