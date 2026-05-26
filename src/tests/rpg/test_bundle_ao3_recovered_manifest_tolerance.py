from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zzzzzzzzzzzzzzzzzzz_bundle_ao3_recovered_manifest_tolerance.pyfrag"
)


def _load_bundle_ao3_namespace(extra_globals=None):
    namespace = {"__name__": "_bundle_ao3_recovered_manifest_tolerance_test"}
    if extra_globals:
        namespace.update(extra_globals)
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _artifact_error(unzipped: Path) -> RuntimeError:
    return RuntimeError(
        "artifact_export_invariant_failed:"
        f"path={unzipped}:"
        "failed_checks=['unzipped_manifest_valid', 'result_zip_manifest_valid']:"
        "missing_unzipped_files=[]:"
        "unzipped_manifest={'ok': False}:"
        "zip_count=0"
    )


def test_bundle_ao3_tolerates_manifest_error_when_recovery_sidecar_present(tmp_path):
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)
    for directory in (parent, unzipped):
        _write_json(directory / "nonfatal-finalization-recovery-summary.json", {"ok": True, "nonfatal_finalization_recovered": True})
        _write_json(directory / "artifact-manifest.json", {"format_version": "bundle_abcd_artifact_manifest_hard_finalized_v1", "source": "bundle_d_hard_artifact_manifest_finalizer", "ok": False})

    namespace = _load_bundle_ao3_namespace()
    exc = _artifact_error(unzipped)

    assert namespace["_bundle_ao3_should_tolerate_manifest_error"](exc) is True
    result = namespace["_bundle_ao3_write_tolerance_sidecars"](namespace["_bundle_ao3_dirs_from_error"](exc), exc)

    assert result["ok"] is True
    assert result["patched_dir_count"] == 2
    for directory in (parent, unzipped):
        manifest = json.loads((directory / "artifact-manifest.json").read_text(encoding="utf-8"))
        sidecar = json.loads((directory / "artifact-manifest-nonfatal-recovery-tolerance-summary.json").read_text(encoding="utf-8"))
        assert manifest["ok"] is True
        assert manifest["advisory_only"] is True
        assert manifest["bundle_ao3_manifest_tolerance_applied"] is True
        assert sidecar["artifact_export_invariant_tolerated"] is True
        assert sidecar["zip_count_before_tolerance"] == 0


def test_bundle_ao3_does_not_tolerate_manifest_error_without_recovery_evidence(tmp_path):
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)
    namespace = _load_bundle_ao3_namespace()

    assert namespace["_bundle_ao3_should_tolerate_manifest_error"](_artifact_error(unzipped)) is False


def test_bundle_ao3_finalizer_wrapper_returns_tolerance_result_for_recovered_manifest(tmp_path):
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)
    for directory in (parent, unzipped):
        _write_json(directory / "nonfatal-finalization-recovery-summary.json", {"ok": True, "nonfatal_finalization_recovered": True})
        _write_json(directory / "artifact-manifest.json", {"ok": False})

    def failing_finalizer():
        raise _artifact_error(unzipped)

    namespace = _load_bundle_ao3_namespace({"_manifest_hard_finalize_latest": failing_finalizer})

    result = namespace["_manifest_hard_finalize_latest"]()

    assert result["ok"] is True
    assert result["patched_dir_count"] == 2
    assert namespace["BUNDLE_AO3_LAST_MANIFEST_TOLERANCE_RESULT"]["ok"] is True
    assert (unzipped / "artifact-manifest-nonfatal-recovery-tolerance-summary.json").exists()


def test_bundle_ao3_finalizer_wrapper_reraises_unrelated_errors():
    def failing_finalizer():
        raise RuntimeError("manifest_corrupt_without_recovery")

    namespace = _load_bundle_ao3_namespace({"_manifest_hard_finalize_latest": failing_finalizer})

    try:
        namespace["_manifest_hard_finalize_latest"]()
    except RuntimeError as exc:
        assert "manifest_corrupt_without_recovery" in str(exc)
    else:
        raise AssertionError("unrelated manifest error should still raise")


def test_bundle_ao3_finalizer_wrapper_reraises_artifact_error_without_recovery(tmp_path):
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)

    def failing_finalizer():
        raise _artifact_error(unzipped)

    namespace = _load_bundle_ao3_namespace({"_manifest_hard_finalize_latest": failing_finalizer})

    try:
        namespace["_manifest_hard_finalize_latest"]()
    except RuntimeError as exc:
        assert "artifact_export_invariant_failed" in str(exc)
    else:
        raise AssertionError("artifact invariant without recovery evidence should still raise")
