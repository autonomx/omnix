from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from app.rpg.session.artifact_export_invariant import (
    enforce_artifact_export_invariant,
    validate_artifact_export_invariant,
)


REQUIRED_EMBEDDED = {
    "quality-gate-summary.json": {"ok": True},
    "survival-exit-criteria-summary.json": {"ok": True},
    "transcript-payload-budget-summary.json": {"ok": True},
    "long-run-dry-run-projection-summary.json": {"ok": True},
    "content-exhaustion-forecast-summary.json": {"ok": True},
    "npc-agency-schedule-summary.json": {"ok": True},
    "economy-resource-pressure-summary.json": {"ok": True},
    "readiness-report-projection-summary.json": {"ok": True},
}


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _manifest() -> dict:
    return {
        "format_version": "bundle_abcd_artifact_manifest_hard_finalized_v1",
        "source": "test",
        "ok": True,
        "hard_finalized": True,
        "embedded_artifacts": dict(REQUIRED_EMBEDDED),
    }


def _seed_core_result_dir(root: Path, *, empty_manifest: bool = False, include_zip: bool = True) -> None:
    root.mkdir(parents=True)
    if empty_manifest:
        (root / "artifact-manifest.json").write_text("", encoding="utf-8")
    else:
        _write_json(root / "artifact-manifest.json", _manifest())
    _write_json(root / "autoplay-health.json", {"ok": True})
    _write_json(root / "summary.json", {"ok": True, "turns_executed": 20})
    _write_json(root / "hundred-turn-evaluation.json", {"ok": True})
    _write_json(root / "readiness-report-projection-summary.json", {"ok": True})
    if include_zip:
        zip_path = root.with_name(root.name[: -len("-unzipped")] + ".zip") if root.name.endswith("-unzipped") else root.parent / "autoplay-campaign-results.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("artifact-manifest.json", json.dumps(_manifest()))
            zf.writestr("autoplay-health.json", json.dumps({"ok": True}))
            zf.writestr("summary.json", json.dumps({"ok": True}))
            zf.writestr("hundred-turn-evaluation.json", json.dumps({"ok": True}))
            zf.writestr("readiness-report-projection-summary.json", json.dumps({"ok": True}))


def test_artifact_export_invariant_passes_valid_unzipped_and_zip_manifest(tmp_path) -> None:
    result_dir = tmp_path / "autoplay-campaign-results-unzipped"
    _seed_core_result_dir(result_dir)

    result = validate_artifact_export_invariant(result_dir)

    assert result["ok"] is True
    assert result["failed_checks"] == []
    assert result["checks"]["unzipped_manifest_valid"] is True
    assert result["checks"]["result_zip_manifest_valid"] is True
    assert result["unzipped_manifest"]["embedded_artifact_count"] == len(REQUIRED_EMBEDDED)


def test_artifact_export_invariant_fails_empty_physical_manifest_even_when_other_files_exist(tmp_path) -> None:
    result_dir = tmp_path / "autoplay-campaign-results-unzipped"
    _seed_core_result_dir(result_dir, empty_manifest=True)

    result = validate_artifact_export_invariant(result_dir)

    assert result["ok"] is False
    assert "required_unzipped_files_present" in result["failed_checks"]
    assert "unzipped_manifest_valid" in result["failed_checks"]
    assert result["unzipped_manifest"]["checks"]["manifest_non_empty_json"] is False


def test_artifact_export_invariant_fails_when_zip_manifest_is_empty(tmp_path) -> None:
    result_dir = tmp_path / "autoplay-campaign-results-unzipped"
    _seed_core_result_dir(result_dir, include_zip=False)
    zip_path = tmp_path / "autoplay-campaign-results.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("artifact-manifest.json", "")

    result = validate_artifact_export_invariant(result_dir)

    assert result["ok"] is False
    assert "result_zip_manifest_valid" in result["failed_checks"]
    assert result["zip_manifest_results"][0]["ok"] is False


def test_artifact_export_invariant_enforcer_raises_clear_runtime_error(tmp_path) -> None:
    result_dir = tmp_path / "autoplay-campaign-results-unzipped"
    _seed_core_result_dir(result_dir, empty_manifest=True)

    with pytest.raises(RuntimeError, match="artifact_export_invariant_failed"):
        enforce_artifact_export_invariant(result_dir)
