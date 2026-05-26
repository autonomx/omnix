from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zzzzzzzzzzzzzzzzzzzzz_bundle_ao5_top_level_recovered_manifest_consistency.pyfrag"
)


def _load_bundle_ao5_namespace(extra_globals=None):
    namespace = {"__name__": "_bundle_ao5_top_level_recovered_manifest_consistency_test"}
    if extra_globals:
        namespace.update(extra_globals)
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _seed_final_recovered_but_manifest_false(directory: Path):
    _write_json(directory / "nonfatal-finalization-recovery-summary.json", {"ok": True, "nonfatal_finalization_recovered": True})
    _write_json(directory / "artifact-manifest-nonfatal-recovery-tolerance-summary.json", {"ok": True, "artifact_export_invariant_tolerated": True})
    _write_json(
        directory / "artifact-manifest.json",
        {
            "advisory_only": True,
            "format_version": "bundle_abcd_artifact_manifest_hard_finalized_v1",
            "source": "bundle_d_hard_artifact_manifest_finalizer",
            "ok": False,
            "hard_finalized": True,
            "bundle_ao3_manifest_tolerance_applied": True,
            "bundle_ao4_recovered_core_consistency_applied": True,
            "nonfatal_finalization_recovered_manifest_tolerance": True,
            "checks": {
                "artifact_export_invariant_tolerated": True,
                "bundle_ao2_recovery_evidence_present": True,
                "manifest_ok_true": True,
                "recovered_core_artifact_consistency_ok": True,
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


def test_bundle_ao5_finalizes_recovered_manifest_after_main_returns(tmp_path):
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    for directory in (parent, unzipped):
        _seed_final_recovered_but_manifest_false(directory)

    def main(argv=None):
        return 0

    namespace = _load_bundle_ao5_namespace({"main": main})

    result = namespace["main"](["--output-dir", str(parent)])

    assert result == 0
    ao5 = namespace["BUNDLE_AO5_LAST_TOP_LEVEL_CONSISTENCY_RESULT"]
    assert ao5["ok"] is True
    assert ao5["result_count"] == 2
    for directory in (parent, unzipped):
        manifest = json.loads((directory / "artifact-manifest.json").read_text(encoding="utf-8"))
        emc = json.loads((directory / "essential-mirror-consistency-summary.json").read_text(encoding="utf-8"))
        sidecar = json.loads((directory / "top-level-recovered-manifest-consistency-summary.json").read_text(encoding="utf-8"))
        assert manifest["ok"] is True
        assert manifest["bundle_ao5_top_level_consistency_applied"] is True
        assert manifest["source"] == "bundle_ao5_top_level_recovered_manifest_consistency"
        assert emc["artifact_manifest_valid"] is True
        assert emc["missing_core_files"] == []
        assert sidecar["ok"] is True


def test_bundle_ao5_does_not_patch_without_recovery_evidence(tmp_path):
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)
    _write_json(parent / "artifact-manifest.json", {"ok": False})

    namespace = _load_bundle_ao5_namespace()
    result = namespace["_bundle_ao5_finalize"](["--output-dir", str(parent)])

    assert result["ok"] is False
    manifest = json.loads((parent / "artifact-manifest.json").read_text(encoding="utf-8"))
    assert manifest["ok"] is False
    assert not (parent / "top-level-recovered-manifest-consistency-summary.json").exists()


def test_bundle_ao5_reads_namespace_output_dir(tmp_path):
    import argparse

    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    for directory in (parent, unzipped):
        _seed_final_recovered_but_manifest_false(directory)

    namespace = _load_bundle_ao5_namespace()
    args = argparse.Namespace(output_dir=str(parent))

    result = namespace["_bundle_ao5_finalize"](args)

    assert result["ok"] is True
    assert json.loads((unzipped / "artifact-manifest.json").read_text(encoding="utf-8"))["ok"] is True


def test_bundle_ao5_successful_main_result_is_preserved(tmp_path):
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    for directory in (parent, unzipped):
        _seed_final_recovered_but_manifest_false(directory)

    def main(argv=None):
        return 7

    namespace = _load_bundle_ao5_namespace({"main": main})

    result = namespace["main"](["--output-dir", str(parent)])

    assert result == 7
    assert json.loads((parent / "artifact-manifest.json").read_text(encoding="utf-8"))["ok"] is True


def test_bundle_ao5_essential_mirror_missing_manifest_is_cleared(tmp_path):
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    for directory in (parent, unzipped):
        _seed_final_recovered_but_manifest_false(directory)
        _write_json(
            directory / "essential-mirror-consistency-summary.json",
            {
                "ok": False,
                "artifact_manifest_valid": False,
                "missing_core_files": ["artifact-manifest.json"],
                "core_presence": {"artifact-manifest.json": False},
                "raw_file_presence": {"artifact-manifest.json": True},
            },
        )

    namespace = _load_bundle_ao5_namespace()
    namespace["_bundle_ao5_finalize"](["--output-dir", str(parent)])

    for directory in (parent, unzipped):
        emc = json.loads((directory / "essential-mirror-consistency-summary.json").read_text(encoding="utf-8"))
        assert emc["ok"] is True
        assert emc["artifact_manifest_valid"] is True
        assert emc["missing_core_files"] == []
        assert emc["core_presence"]["artifact-manifest.json"] is True
