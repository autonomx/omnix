from __future__ import annotations

import json
from pathlib import Path

from app.rpg.session.autoplay_manifest_hard_finalize import hard_finalize_artifact_manifest


BUNDLE_A = {
    "quality-gate-summary.json": {"ok": True, "source": "quality"},
    "survival-exit-criteria-summary.json": {"ok": True, "source": "survival", "drink_water_count": 4},
    "transcript-payload-budget-summary.json": {"ok": True, "advisory_ok": True, "source": "payload", "projected_1000_turn_transcript_bytes": 444000},
}
BUNDLE_B = {
    "long-run-dry-run-projection-summary.json": {"ok": True, "advisory_ok": True, "source": "long_run"},
    "content-exhaustion-forecast-summary.json": {"ok": True, "advisory_ok": True, "source": "content"},
}
BUNDLE_C = {
    "npc-agency-schedule-summary.json": {"ok": True, "advisory_ok": True, "source": "npc", "npc_count": 3},
    "economy-resource-pressure-summary.json": {"ok": True, "advisory_ok": True, "source": "economy", "paid_count": 12},
}
BUNDLE_D = {
    "readiness-report-projection-summary.json": {"ok": True, "advisory_ok": True, "source": "projection", "section_count": 6},
}
ALL_BUNDLES = {**BUNDLE_A, **BUNDLE_B, **BUNDLE_C, **BUNDLE_D}


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _seed_result_dir(root: Path, *, empty_manifest: bool = True) -> None:
    root.mkdir(parents=True)
    _write_json(root / "hundred-turn-evaluation.json", {"ok": True, "artifact_level_summaries": {}})
    _write_json(root / "hundred-turn-readiness-summary.json", {"ok": True, "failed_gates": []})
    _write_json(root / "autoplay-health.json", {"ok": True})
    for filename, payload in ALL_BUNDLES.items():
        _write_json(root / filename, payload)
    if empty_manifest:
        (root / "artifact-manifest.json").write_text("", encoding="utf-8")
    else:
        _write_json(root / "artifact-manifest.json", {"ok": False, "files": [], "embedded_artifacts": {}})


def test_hard_finalize_rebuilds_empty_artifact_manifest_from_physical_bundle_files(tmp_path) -> None:
    result_dir = tmp_path / "autoplay-campaign-results-unzipped"
    _seed_result_dir(result_dir, empty_manifest=True)

    result = hard_finalize_artifact_manifest(result_dir)

    assert result["applied"] is True
    assert result["manifest_ok"] is True
    assert result["manifest_size"] > 2
    assert result["final_write_after_all_wrappers"] is True

    manifest_path = result_dir / "artifact-manifest.json"
    assert manifest_path.stat().st_size == result["manifest_size"]
    manifest = _read_json(manifest_path)
    assert manifest["format_version"] == "bundle_abcd_artifact_manifest_hard_finalized_v1"
    assert manifest["source"] == "bundle_d_hard_artifact_manifest_finalizer"
    assert manifest["ok"] is True
    assert manifest["hard_finalized"] is True
    assert manifest["final_write_after_all_wrappers"] is True
    assert manifest["physical_presence"] == {name: True for name in BUNDLE_A}
    assert manifest["bundle_b_physical_presence"] == {name: True for name in BUNDLE_B}
    assert manifest["bundle_c_physical_presence"] == {name: True for name in BUNDLE_C}
    assert manifest["bundle_d_physical_presence"] == {name: True for name in BUNDLE_D}
    for filename in ALL_BUNDLES:
        assert filename in manifest["files"]
        assert manifest["embedded_artifacts"][filename]["ok"] is True


def test_hard_finalize_patches_sidecars_and_keeps_manifest_as_final_write(tmp_path) -> None:
    result_dir = tmp_path / "autoplay-campaign-results-unzipped"
    _seed_result_dir(result_dir, empty_manifest=False)

    result = hard_finalize_artifact_manifest(result_dir)

    assert result["applied"] is True
    manifest = _read_json(result_dir / "artifact-manifest.json")
    assert manifest["hard_finalized"] is True

    health = _read_json(result_dir / "autoplay-health.json")
    assert health["artifact_manifest_hard_finalized"]["applied"] is True
    assert health["artifact_manifest_hard_finalized"]["ok"] is True
    assert health["artifact_manifest_hard_finalized"]["final_write_after_all_wrappers"] is True

    evaluation = _read_json(result_dir / "hundred-turn-evaluation.json")
    summary = evaluation["artifact_level_summaries"]["artifact-manifest.json"]
    assert summary["hard_finalized"] is True
    assert summary["final_write_after_all_wrappers"] is True
    assert summary["format_version"] == "bundle_abcd_artifact_manifest_hard_finalized_v1"

    readiness = _read_json(result_dir / "hundred-turn-readiness-summary.json")
    assert readiness["artifact_manifest_hard_finalized"]["applied"] is True
    assert readiness["artifact_manifest_hard_finalized"]["ok"] is True

    # The manifest is rewritten after the sidecar patches, so it remains readable
    # and non-empty after health/evaluation/readiness have been updated.
    final_manifest = _read_json(result_dir / "artifact-manifest.json")
    assert final_manifest["final_write_after_all_wrappers"] is True
    assert final_manifest["embedded_artifacts"]["readiness-report-projection-summary.json"]["ok"] is True


def test_hard_finalize_skips_when_evaluation_is_missing(tmp_path) -> None:
    result_dir = tmp_path / "autoplay-campaign-results-unzipped"
    result_dir.mkdir(parents=True)
    (result_dir / "artifact-manifest.json").write_text("", encoding="utf-8")

    result = hard_finalize_artifact_manifest(result_dir)

    assert result["applied"] is False
    assert result["reason"] == "evaluation_missing"
    assert (result_dir / "artifact-manifest.json").read_text(encoding="utf-8") == ""
