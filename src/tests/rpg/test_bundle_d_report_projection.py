from __future__ import annotations

import json
from pathlib import Path

from app.rpg.session.bundle_d_report_projection import (
    REPORT_PROJECTION_FILE,
    build_readiness_report_projection_summary,
    write_bundle_d_artifacts,
)


ARTIFACTS = {
    "survival-exit-criteria-summary.json": {"ok": True, "drink_water_count": 4, "eat_food_count": 2, "blocked_relief_count": 0, "capped_thirst_turns": 0},
    "transcript-payload-budget-summary.json": {"ok": True, "advisory_ok": True, "projected_1000_turn_transcript_bytes": 444000, "oversized_row_count": 0},
    "long-run-dry-run-projection-summary.json": {"ok": True, "advisory_ok": True, "target_profiles": [{"target_turns": 300}], "recommended_next_run": {"profile": "dry_run_300"}},
    "content-exhaustion-forecast-summary.json": {"ok": True, "advisory_ok": True, "classification": "content_sufficient_for_requested_turns", "turns_until_content_exhaustion_estimate": 200},
    "npc-agency-schedule-summary.json": {"ok": True, "npc_count": 3, "schedule_event_count": 32, "memory_event_count": 182},
    "economy-resource-pressure-summary.json": {"ok": True, "paid_count": 12, "unpaid_count": 0, "total_spent": {"gold": 7}, "ending_currency": {"gold": 3}},
}


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _seed_result_dir(root: Path, *, embed: bool = True) -> None:
    root.mkdir(parents=True)
    _write_json(root / "hundred-turn-evaluation.json", {"ok": True, "artifact_level_summaries": {}})
    _write_json(root / "hundred-turn-readiness-summary.json", {"ok": True, "failed_gates": []})
    _write_json(root / "autoplay-health.json", {"ok": True})
    for name, payload in ARTIFACTS.items():
        _write_json(root / name, payload)
    manifest = {
        "format_version": "bundle_abc_artifact_manifest_v2",
        "ok": True,
        "final_write_after_sidecars": True,
        "embedded_artifacts": dict(ARTIFACTS) if embed else {},
    }
    _write_json(root / "artifact-manifest.json", manifest)


def test_bundle_d_projection_passes_for_green_bundle_artifacts(tmp_path) -> None:
    result_dir = tmp_path / "autoplay-campaign-results-unzipped"
    _seed_result_dir(result_dir)
    evaluation = json.loads((result_dir / "hundred-turn-evaluation.json").read_text(encoding="utf-8"))
    readiness = json.loads((result_dir / "hundred-turn-readiness-summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((result_dir / "artifact-manifest.json").read_text(encoding="utf-8"))

    projection = build_readiness_report_projection_summary(evaluation, readiness, manifest, root=result_dir)

    assert projection["ok"] is True
    assert projection["section_count"] == 6
    assert projection["checks"]["all_report_sections_ok"] is True
    assert projection["checks"]["all_sections_manifest_embedded"] is True
    assert {section["id"] for section in projection["sections"]} == {
        "survival-exit-criteria",
        "transcript-payload-budget",
        "long-run-dry-run-projection",
        "content-exhaustion-forecast",
        "npc-agency-schedule",
        "economy-resource-pressure",
    }


def test_bundle_d_projection_flags_missing_manifest_embedding(tmp_path) -> None:
    result_dir = tmp_path / "autoplay-campaign-results-unzipped"
    _seed_result_dir(result_dir, embed=False)
    evaluation = json.loads((result_dir / "hundred-turn-evaluation.json").read_text(encoding="utf-8"))
    readiness = json.loads((result_dir / "hundred-turn-readiness-summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((result_dir / "artifact-manifest.json").read_text(encoding="utf-8"))

    projection = build_readiness_report_projection_summary(evaluation, readiness, manifest, root=result_dir)

    assert projection["ok"] is False
    assert "all_sections_manifest_embedded" in projection["failed_checks"]
    assert projection["checks"]["all_report_sections_ok"] is True


def test_bundle_d_writer_patches_health_evaluation_and_manifest(tmp_path) -> None:
    result_dir = tmp_path / "autoplay-campaign-results-unzipped"
    _seed_result_dir(result_dir)

    result = write_bundle_d_artifacts(result_dir)

    assert result["applied"] is True
    assert result["readiness_report_projection_ok"] is True
    assert (result_dir / REPORT_PROJECTION_FILE).exists()
    projection = json.loads((result_dir / REPORT_PROJECTION_FILE).read_text(encoding="utf-8"))
    assert projection["ok"] is True

    manifest = json.loads((result_dir / "artifact-manifest.json").read_text(encoding="utf-8"))
    assert REPORT_PROJECTION_FILE in manifest["bundle_d_files"]
    assert manifest["embedded_artifacts"][REPORT_PROJECTION_FILE]["ok"] is True

    health = json.loads((result_dir / "autoplay-health.json").read_text(encoding="utf-8"))
    assert health["bundle_d_artifacts_ok"] is True
    assert health["readiness_report_projection_ok"] is True

    evaluation = json.loads((result_dir / "hundred-turn-evaluation.json").read_text(encoding="utf-8"))
    assert evaluation["bundle_d_artifacts"]["readiness_report_projection_ok"] is True
    assert evaluation["artifact_level_summaries"][REPORT_PROJECTION_FILE]["ok"] is True
