from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zzzzzzzzzzzzzzzzzzzz_bundle_ao4_recovered_core_artifact_consistency.pyfrag"
)


def _load_bundle_ao4_namespace(extra_globals=None):
    namespace = {"__name__": "_bundle_ao4_recovered_core_artifact_consistency_test"}
    if extra_globals:
        namespace.update(extra_globals)
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _seed_recovered_manifest_case(directory: Path):
    _write_json(directory / "nonfatal-finalization-recovery-summary.json", {"ok": True, "nonfatal_finalization_recovered": True})
    _write_json(directory / "artifact-manifest-nonfatal-recovery-tolerance-summary.json", {"ok": True, "artifact_export_invariant_tolerated": True})
    _write_json(
        directory / "artifact-manifest.json",
        {
            "format_version": "bundle_abcd_artifact_manifest_hard_finalized_v1",
            "source": "bundle_d_hard_artifact_manifest_finalizer",
            "ok": False,
            "hard_finalized": True,
            "embedded_artifacts": {"summary.json": {}},
            "checks": {"manifest_ok_true": False},
        },
    )
    _write_json(
        directory / "essential-mirror-consistency-summary.json",
        {
            "format_version": "bundle_d_results_mirror_extraction_repair_v3",
            "source": "bundle_d_results_mirror_extraction_repair",
            "ok": False,
            "core_presence": {"artifact-manifest.json": False, "summary.json": True},
            "raw_file_presence": {"artifact-manifest.json": True, "summary.json": True},
            "artifact_manifest_valid": False,
            "missing_core_files": ["artifact-manifest.json"],
        },
    )


def test_bundle_ao4_patches_recovered_manifest_and_mirror_consistency(tmp_path):
    namespace = _load_bundle_ao4_namespace()
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    for directory in (parent, unzipped):
        _seed_recovered_manifest_case(directory)

    result = namespace["_bundle_ao4_finalize"](parent)

    assert result["ok"] is True
    assert result["result_count"] == 2
    for directory in (parent, unzipped):
        manifest = json.loads((directory / "artifact-manifest.json").read_text(encoding="utf-8"))
        emc = json.loads((directory / "essential-mirror-consistency-summary.json").read_text(encoding="utf-8"))
        sidecar = json.loads((directory / "recovered-core-artifact-consistency-summary.json").read_text(encoding="utf-8"))
        assert manifest["ok"] is True
        assert manifest["bundle_ao4_recovered_core_consistency_applied"] is True
        assert manifest["checks"]["manifest_ok_true"] is True
        assert emc["artifact_manifest_valid"] is True
        assert emc["core_presence"]["artifact-manifest.json"] is True
        assert "artifact-manifest.json" not in emc["missing_core_files"]
        assert sidecar["ok"] is True


def test_bundle_ao4_does_not_patch_without_recovery_evidence(tmp_path):
    namespace = _load_bundle_ao4_namespace()
    directory = tmp_path / "autoplay-output"
    directory.mkdir()
    _write_json(directory / "artifact-manifest.json", {"ok": False})
    _write_json(directory / "essential-mirror-consistency-summary.json", {"ok": False, "missing_core_files": ["artifact-manifest.json"]})

    result = namespace["_bundle_ao4_finalize"](directory)

    assert result["ok"] is False
    manifest = json.loads((directory / "artifact-manifest.json").read_text(encoding="utf-8"))
    assert manifest["ok"] is False
    assert not (directory / "recovered-core-artifact-consistency-summary.json").exists()


def test_bundle_ao4_write_text_wrapper_triggers_after_manifest_write(tmp_path):
    _load_bundle_ao4_namespace()
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    for directory in (parent, unzipped):
        _seed_recovered_manifest_case(directory)

    (unzipped / "artifact-manifest.json").write_text(json.dumps({"ok": False, "embedded_artifacts": {}}), encoding="utf-8")

    manifest = json.loads((unzipped / "artifact-manifest.json").read_text(encoding="utf-8"))
    emc = json.loads((unzipped / "essential-mirror-consistency-summary.json").read_text(encoding="utf-8"))
    assert manifest["ok"] is True
    assert emc["artifact_manifest_valid"] is True


def test_bundle_ao4_manifest_finalizer_wrapper_reapplies_after_ao3_result(tmp_path):
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    for directory in (parent, unzipped):
        _seed_recovered_manifest_case(directory)

    def finalizer():
        return {"ok": True}

    namespace = _load_bundle_ao4_namespace(
        {
            "_manifest_hard_finalize_latest": finalizer,
            "BUNDLE_AO3_LAST_MANIFEST_TOLERANCE_RESULT": {"patched_dirs": [str(parent), str(unzipped)]},
        }
    )

    result = namespace["_manifest_hard_finalize_latest"]()

    assert result["ok"] is True
    for directory in (parent, unzipped):
        manifest = json.loads((directory / "artifact-manifest.json").read_text(encoding="utf-8"))
        assert manifest["ok"] is True


def test_bundle_ao4_parent_unzipped_pair_from_unzipped_path(tmp_path):
    namespace = _load_bundle_ao4_namespace()
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)

    resolved_parent, resolved_unzipped = namespace["_bundle_ao4_parent_unzipped"](unzipped / "artifact-manifest.json")

    assert resolved_parent == parent
    assert resolved_unzipped == unzipped
