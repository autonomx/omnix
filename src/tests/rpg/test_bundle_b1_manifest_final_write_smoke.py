from __future__ import annotations

import json
from pathlib import Path

from app.rpg.session.bundle_a_manifest_repair import repair_bundle_a_manifest


BUNDLE_A_FILES = {
    "quality-gate-summary.json": {"ok": True, "source": "test_quality"},
    "survival-exit-criteria-summary.json": {"ok": True, "source": "test_survival", "drink_water_count": 4},
    "transcript-payload-budget-summary.json": {"ok": True, "advisory_ok": True, "source": "test_payload", "projected_1000_turn_transcript_bytes": 444000},
}

BUNDLE_B_FILES = {
    "long-run-dry-run-projection-summary.json": {"ok": True, "advisory_ok": True, "source": "test_long_run", "recommended_next_run": {"profile": "dry_run_300"}},
    "content-exhaustion-forecast-summary.json": {"ok": True, "advisory_ok": True, "source": "test_content", "classification": "content_sufficient_for_requested_turns"},
}

BUNDLE_C_FILES = {
    "npc-agency-schedule-summary.json": {"ok": True, "advisory_ok": True, "source": "test_npc", "npc_count": 3, "schedule_event_count": 32},
    "economy-resource-pressure-summary.json": {"ok": True, "advisory_ok": True, "source": "test_economy", "paid_count": 12, "unpaid_count": 0},
}


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _seed_result_dir(result_dir: Path) -> None:
    result_dir.mkdir(parents=True)
    _write_json(
        result_dir / "hundred-turn-evaluation.json",
        {
            "ok": True,
            "turns_executed": 5,
            "requested_turns": 5,
            "artifact_level_summaries": {},
        },
    )
    _write_json(result_dir / "hundred-turn-readiness-summary.json", {"ok": True, "failed_gates": []})
    _write_json(result_dir / "autoplay-health.json", {"ok": True})
    for filename, payload in {**BUNDLE_A_FILES, **BUNDLE_B_FILES, **BUNDLE_C_FILES}.items():
        _write_json(result_dir / filename, payload)
    # Simulate the exact observed failure mode from the 100-turn run.
    (result_dir / "artifact-manifest.json").write_text("", encoding="utf-8")


def test_bundle_b1_manifest_repair_final_write_survives_sidecar_patches(tmp_path) -> None:
    result_dir = tmp_path / "autoplay-campaign-results-unzipped"
    _seed_result_dir(result_dir)

    result = repair_bundle_a_manifest(result_dir)

    assert result["applied"] is True
    assert result["final_write_after_sidecars"] is True
    assert result["manifest_exists_after_final_write"] is True

    manifest_path = result_dir / "artifact-manifest.json"
    assert manifest_path.exists()
    assert manifest_path.stat().st_size > 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["format_version"] == "bundle_abc_artifact_manifest_v2"
    assert manifest["ok"] is True
    assert manifest["final_write_after_sidecars"] is True
    assert manifest["physical_presence"] == {name: True for name in BUNDLE_A_FILES}
    assert manifest["bundle_b_physical_presence"] == {name: True for name in BUNDLE_B_FILES}
    assert manifest["bundle_c_physical_presence"] == {name: True for name in BUNDLE_C_FILES}
    for filename in [*BUNDLE_A_FILES, *BUNDLE_B_FILES, *BUNDLE_C_FILES]:
        assert filename in manifest["embedded_artifacts"]
        assert manifest["embedded_artifacts"][filename]["ok"] is True

    health = json.loads((result_dir / "autoplay-health.json").read_text(encoding="utf-8"))
    assert health["bundle_a_manifest_repair"]["final_write_after_sidecars"] is True
    assert health["bundle_b_manifest_repair"]["final_write_after_sidecars"] is True
    assert health["bundle_c_manifest_repair"]["final_write_after_sidecars"] is True

    evaluation = json.loads((result_dir / "hundred-turn-evaluation.json").read_text(encoding="utf-8"))
    assert evaluation["artifact_level_summaries"]["artifact-manifest.json"]["final_write_after_sidecars"] is True
