from __future__ import annotations

import json

from app.rpg.session.bundle_ab_late_manifest_hook import register_late_manifest_repair
from app.rpg.session.bundle_b_artifacts import (
    build_content_exhaustion_forecast_summary,
    build_long_run_dry_run_projection_summary,
    write_bundle_b_artifacts,
)


def _evaluation():
    return {
        "ok": True,
        "requested_turns": 100,
        "turns_executed": 100,
        "gates": {
            "performance_turn_latency": {
                "ok": True,
                "value": {"avg_turn_seconds": 6.0, "p95_turn_seconds": 9.0},
            },
            "world_state_compression_active": {
                "ok": True,
                "value": {
                    "latest_state_budget": {
                        "ok": True,
                        "sections": {
                            "summary": {"bytes": 3000, "ok": True},
                            "story_arcs": {"bytes": 1500, "ok": True},
                            "world_signals": {"bytes": 1000, "ok": True},
                        },
                    }
                },
            },
            "story_arc_resolution_present": {"ok": True, "value": {"completed_count": 2}},
            "followup_arc_progression_present": {"ok": True, "value": {"progression_event_count": 50}},
            "escalation_arc_progression_present": {"ok": True, "value": {"progression_event_count": 20}},
            "pressure_pacing_active": {"ok": True, "value": {"accepted_pressure_count": 10}},
        },
        "artifact_level_summaries": {},
    }


def _readiness():
    return {
        "ok": True,
        "requested_turns": 100,
        "classification": "content_sufficient_for_requested_turns",
        "progression_changed_count": 100,
        "unique_progression_node_count": 100,
        "graph_count": 9,
        "completed_graph_count": 8,
        "campaign_graphs_complete": False,
        "waiting_for_next_graph_pack": False,
    }


def _payload_budget():
    return {
        "ok": True,
        "advisory_ok": True,
        "average_row_bytes": 500,
        "projected_1000_turn_transcript_bytes": 500000,
    }


def _survival_exit():
    return {"ok": True, "drink_water_count": 4, "blocked_relief_count": 0}


def test_n130_long_run_projection_summary_passes_for_green_100_turn_run() -> None:
    summary = build_long_run_dry_run_projection_summary(
        _evaluation(),
        _readiness(),
        _payload_budget(),
        _survival_exit(),
    )

    assert summary["ok"] is True
    assert summary["failed_checks"] == []
    assert summary["recommended_next_run"]["profile"] == "dry_run_300"
    by_turns = {item["target_turns"]: item for item in summary["target_profiles"]}
    assert by_turns[250]["projected_wall_seconds_avg"] == 1500.0
    assert by_turns[300]["projected_transcript_bytes"] == 150000
    assert by_turns[1000]["projected_transcript_bytes"] == 500000


def test_n130_long_run_projection_flags_payload_budget_regression() -> None:
    payload = _payload_budget()
    payload["advisory_ok"] = False
    payload["projected_1000_turn_transcript_bytes"] = 2_000_000_000

    summary = build_long_run_dry_run_projection_summary(
        _evaluation(),
        _readiness(),
        payload,
        _survival_exit(),
    )

    assert summary["ok"] is False
    assert "payload_budget_advisory_ok" in summary["failed_checks"]
    assert "profile_1000_transcript_budget_ok" in summary["failed_checks"]


def test_n131_content_exhaustion_forecast_passes_for_sufficient_content() -> None:
    summary = build_content_exhaustion_forecast_summary(_evaluation(), _readiness())

    assert summary["ok"] is True
    assert summary["classification"] == "content_sufficient_for_requested_turns"
    assert summary["graph_count"] == 9
    assert summary["completed_graph_count"] == 8
    assert summary["available_next_graph_count"] == 1
    assert summary["graph_progression_density"] == 1.0
    assert summary["turns_until_content_exhaustion_estimate"] >= 100


def test_n131_content_exhaustion_forecast_flags_exhausted_content() -> None:
    readiness = _readiness()
    readiness["classification"] = "content_exhausted"
    readiness["campaign_graphs_complete"] = True
    readiness["waiting_for_next_graph_pack"] = True
    readiness["progression_changed_count"] = 2
    readiness["unique_progression_node_count"] = 2

    summary = build_content_exhaustion_forecast_summary(_evaluation(), readiness)

    assert summary["ok"] is False
    assert "readiness_content_classification_ok" in summary["failed_checks"]
    assert "waiting_for_next_graph_pack_ok" in summary["failed_checks"]
    assert "campaign_graphs_not_fully_exhausted_ok" in summary["failed_checks"]


def test_bundle_b_writes_expected_artifacts_and_manifest(tmp_path) -> None:
    result_dir = tmp_path / "autoplay-campaign-results-unzipped"
    result_dir.mkdir()
    evaluation = _evaluation()
    readiness = _readiness()
    (result_dir / "hundred-turn-evaluation.json").write_text(json.dumps(evaluation), encoding="utf-8")
    (result_dir / "hundred-turn-readiness-summary.json").write_text(json.dumps(readiness), encoding="utf-8")
    (result_dir / "autoplay-health.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (result_dir / "transcript-payload-budget-summary.json").write_text(json.dumps(_payload_budget()), encoding="utf-8")
    (result_dir / "survival-exit-criteria-summary.json").write_text(json.dumps(_survival_exit()), encoding="utf-8")
    (result_dir / "artifact-manifest.json").write_text(json.dumps({"ok": True, "files": [], "embedded_artifacts": {}}), encoding="utf-8")

    result = write_bundle_b_artifacts(result_dir)

    assert result["applied"] is True
    assert result["long_run_projection_ok"] is True
    assert result["content_exhaustion_forecast_ok"] is True
    assert (result_dir / "long-run-dry-run-projection-summary.json").exists()
    assert (result_dir / "content-exhaustion-forecast-summary.json").exists()
    manifest = json.loads((result_dir / "artifact-manifest.json").read_text(encoding="utf-8"))
    assert "long-run-dry-run-projection-summary.json" in manifest["bundle_b_files"]
    assert "content-exhaustion-forecast-summary.json" in manifest["bundle_b_files"]
    assert manifest["embedded_artifacts"]["long-run-dry-run-projection-summary.json"]["ok"] is True
    health = json.loads((result_dir / "autoplay-health.json").read_text(encoding="utf-8"))
    assert health["bundle_b_artifacts_ok"] is True
    assert health["long_run_projection_ok"] is True
    assert health["content_exhaustion_forecast_ok"] is True
    patched_eval = json.loads((result_dir / "hundred-turn-evaluation.json").read_text(encoding="utf-8"))
    assert patched_eval["bundle_b_artifacts"]["long_run_projection_ok"] is True


def test_bundle_b_empty_manifest_write_guard_rebuilds_manifest(tmp_path) -> None:
    result_dir = tmp_path / "autoplay-campaign-results-unzipped"
    result_dir.mkdir()
    (result_dir / "hundred-turn-evaluation.json").write_text(json.dumps(_evaluation()), encoding="utf-8")
    (result_dir / "hundred-turn-readiness-summary.json").write_text(json.dumps(_readiness()), encoding="utf-8")
    (result_dir / "autoplay-health.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (result_dir / "quality-gate-summary.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (result_dir / "survival-exit-criteria-summary.json").write_text(json.dumps(_survival_exit()), encoding="utf-8")
    (result_dir / "transcript-payload-budget-summary.json").write_text(json.dumps(_payload_budget()), encoding="utf-8")
    write_bundle_b_artifacts(result_dir)

    register_late_manifest_repair([result_dir])
    (result_dir / "artifact-manifest.json").write_text("", encoding="utf-8")

    manifest = json.loads((result_dir / "artifact-manifest.json").read_text(encoding="utf-8"))
    assert manifest["empty_write_guard_applied"] is True
    assert manifest["ok"] is True
    assert "quality-gate-summary.json" in manifest["embedded_artifacts"]
    assert "long-run-dry-run-projection-summary.json" in manifest["embedded_artifacts"]
    assert "content-exhaustion-forecast-summary.json" in manifest["embedded_artifacts"]
