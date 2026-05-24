from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app.rpg.session.autoplay_results_mirror_repair import repair_results_mirror_from_zip


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


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest() -> dict:
    return {
        "format_version": "bundle_abcd_artifact_manifest_hard_finalized_v1",
        "source": "test",
        "ok": True,
        "hard_finalized": True,
        "final_write_after_all_wrappers": True,
        "embedded_artifacts": dict(REQUIRED_EMBEDDED),
    }


def test_results_mirror_repair_extracts_full_unzipped_folder_from_zip(tmp_path) -> None:
    result_dir = tmp_path / "autoplay-campaign-results-unzipped"
    result_dir.mkdir(parents=True)
    _write_json(
        result_dir / "essential-mirror-consistency-summary.json",
        {
            "format_version": "n1221_essential_mirror_consistency_v1",
            "ok": True,
            "expected_file_count": 47,
            "present_expected_file_count": 1,
        },
    )
    zip_path = tmp_path / "autoplay-campaign-results.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("artifact-manifest.json", json.dumps(_manifest()))
        zf.writestr("autoplay-health.json", json.dumps({"ok": True}))
        zf.writestr("summary.json", json.dumps({"ok": True, "turns_executed": 20}))
        zf.writestr("hundred-turn-evaluation.json", json.dumps({"ok": True, "artifact_level_summaries": {}}))
        zf.writestr("hundred-turn-readiness-summary.json", json.dumps({"ok": True}))
        zf.writestr("readiness-report-projection-summary.json", json.dumps({"ok": True, "section_count": 6}))

    result = repair_results_mirror_from_zip(result_dir)

    assert result["ok"] is True
    assert result["after_has_core"] is True
    assert result["extracted_file_count"] >= 6
    assert result["digest"]["ok"] is True
    assert _read_json(result_dir / "artifact-manifest.json")["hard_finalized"] is True
    assert _read_json(result_dir / "autoplay-health.json")["ok"] is True
    digest = _read_json(result_dir / "artifact-manifest-digest.json")
    assert digest["ok"] is True
    assert digest["embedded_artifact_count"] == len(REQUIRED_EMBEDDED)
    mirror = _read_json(result_dir / "essential-mirror-consistency-summary.json")
    assert mirror["format_version"] == "bundle_d_results_mirror_extraction_repair_v3"
    assert mirror["ok"] is True
    assert mirror["repaired"] is True
    assert mirror["artifact_manifest_digest_ok"] is True
    assert mirror["artifact_manifest_digest"]["embedded_artifact_count"] == len(REQUIRED_EMBEDDED)
    assert mirror["core_presence"] == {
        "artifact-manifest.json": True,
        "autoplay-health.json": True,
        "summary.json": True,
        "hundred-turn-evaluation.json": True,
    }


def test_results_mirror_repair_marks_incomplete_without_zip(tmp_path) -> None:
    result_dir = tmp_path / "autoplay-campaign-results-unzipped"
    result_dir.mkdir(parents=True)
    _write_json(result_dir / "essential-mirror-consistency-summary.json", {"ok": True})

    result = repair_results_mirror_from_zip(result_dir)

    assert result["ok"] is False
    assert result["after_has_core"] is False
    mirror = _read_json(result_dir / "essential-mirror-consistency-summary.json")
    assert mirror["ok"] is False
    assert "artifact-manifest.json" in mirror["missing_core_files"]
