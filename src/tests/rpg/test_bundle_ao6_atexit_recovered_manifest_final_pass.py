from __future__ import annotations

import argparse
import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zzzzzzzzzzzzzzzzzzzzzz_bundle_ao6_atexit_recovered_manifest_final_pass.pyfrag"
)


def _load_bundle_ao6_namespace(extra_globals=None):
    namespace = {"__name__": "_bundle_ao6_atexit_recovered_manifest_final_pass_test"}
    if extra_globals:
        namespace.update(extra_globals)
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _seed_ao5_flags_but_manifest_false(directory: Path):
    _write_json(directory / "nonfatal-finalization-recovery-summary.json", {"ok": True, "nonfatal_finalization_recovered": True})
    _write_json(
        directory / "artifact-manifest.json",
        {
            "advisory_only": True,
            "format_version": "bundle_abcd_artifact_manifest_hard_finalized_v1",
            "source": "bundle_d_hard_artifact_manifest_finalizer",
            "ok": False,
            "hard_finalized": True,
            "bundle_ao5_top_level_consistency_applied": True,
            "bundle_ao4_recovered_core_consistency_applied": True,
            "bundle_ao3_manifest_tolerance_applied": True,
            "nonfatal_finalization_recovered_manifest_tolerance": True,
            "checks": {
                "artifact_export_invariant_tolerated": True,
                "bundle_ao2_recovery_evidence_present": True,
                "manifest_ok_true": True,
                "recovered_core_artifact_consistency_ok": True,
                "top_level_recovered_manifest_consistency_ok": True,
            },
        },
    )
    _write_json(
        directory / "essential-mirror-consistency-summary.json",
        {
            "ok": True,
            "artifact_manifest_valid": True,
            "artifact_manifest_recovered_advisory_valid": True,
            "missing_core_files": [],
            "core_presence": {"artifact-manifest.json": True},
            "raw_file_presence": {"artifact-manifest.json": True},
        },
    )


def test_bundle_ao6_finalizes_unzipped_manifest_with_ao5_flags_but_ok_false(tmp_path):
    namespace = _load_bundle_ao6_namespace()
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    for directory in (parent, unzipped):
        _seed_ao5_flags_but_manifest_false(directory)

    result = namespace["_bundle_ao6_finalize_output_dir"](str(parent))

    assert result["ok"] is True
    assert result["result_count"] == 2
    for directory in (parent, unzipped):
        manifest = json.loads((directory / "artifact-manifest.json").read_text(encoding="utf-8"))
        emc = json.loads((directory / "essential-mirror-consistency-summary.json").read_text(encoding="utf-8"))
        sidecar = json.loads((directory / "atexit-recovered-manifest-final-pass-summary.json").read_text(encoding="utf-8"))
        assert manifest["ok"] is True
        assert manifest["bundle_ao6_atexit_final_pass_applied"] is True
        assert manifest["checks"]["atexit_recovered_manifest_final_pass_ok"] is True
        assert emc["artifact_manifest_valid"] is True
        assert emc["missing_core_files"] == []
        assert sidecar["ok"] is True


def test_bundle_ao6_main_wrapper_records_output_dir_and_runs_final_pass(tmp_path):
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    for directory in (parent, unzipped):
        _seed_ao5_flags_but_manifest_false(directory)

    def main(argv=None):
        return 0

    namespace = _load_bundle_ao6_namespace({"main": main})

    result = namespace["main"](["--output-dir", str(parent)])

    assert result == 0
    assert namespace["BUNDLE_AO6_LAST_OUTPUT_DIR"] == str(parent)
    assert namespace["BUNDLE_AO6_ATEXIT_RESULT"]["ok"] is True
    assert json.loads((unzipped / "artifact-manifest.json").read_text(encoding="utf-8"))["ok"] is True


def test_bundle_ao6_main_wrapper_handles_namespace_args(tmp_path):
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    for directory in (parent, unzipped):
        _seed_ao5_flags_but_manifest_false(directory)

    def main(argv=None):
        return 3

    namespace = _load_bundle_ao6_namespace({"main": main})

    result = namespace["main"](argparse.Namespace(output_dir=str(parent)))

    assert result == 3
    assert json.loads((parent / "artifact-manifest.json").read_text(encoding="utf-8"))["ok"] is True
    assert json.loads((unzipped / "artifact-manifest.json").read_text(encoding="utf-8"))["ok"] is True


def test_bundle_ao6_does_not_patch_without_recovery_evidence(tmp_path):
    namespace = _load_bundle_ao6_namespace()
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)
    _write_json(parent / "artifact-manifest.json", {"ok": False})

    result = namespace["_bundle_ao6_finalize_output_dir"](str(parent))

    assert result["ok"] is False
    assert json.loads((parent / "artifact-manifest.json").read_text(encoding="utf-8"))["ok"] is False
    assert not (parent / "atexit-recovered-manifest-final-pass-summary.json").exists()


def test_bundle_ao6_atexit_run_uses_recorded_output_dir(tmp_path):
    namespace = _load_bundle_ao6_namespace()
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    for directory in (parent, unzipped):
        _seed_ao5_flags_but_manifest_false(directory)
    namespace["BUNDLE_AO6_LAST_OUTPUT_DIR"] = str(parent)

    namespace["_bundle_ao6_atexit_run"]()

    assert namespace["BUNDLE_AO6_ATEXIT_RESULT"]["ok"] is True
    assert json.loads((unzipped / "artifact-manifest.json").read_text(encoding="utf-8"))["ok"] is True
