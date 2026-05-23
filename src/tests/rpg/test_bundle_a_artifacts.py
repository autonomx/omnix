from __future__ import annotations

import json

from app.rpg.session.bundle_a_artifacts import (
    build_survival_exit_criteria_summary,
    build_transcript_payload_budget_summary,
    write_bundle_a_artifacts,
)
from app.rpg.session.quality_gate_artifact_repair import repair_quality_gate_artifacts


def _evaluation():
    survival_pressure = {
        "relief_counts_by_kind": {"drink_water": 4, "eat_food": 2, "rest": 1},
        "blocked_relief_count": 0,
        "blocked_counts_by_reason": {},
        "inventory_consumed_summary": [
            {"item_id": "autoplay_waterskin_4", "name": "Autoplay Waterskin", "quantity": 1},
            {"item_id": "emergency_water_cache_1", "name": "Emergency Water Cache", "quantity": 3},
            {"item_id": "autoplay_field_ration_1", "name": "Autoplay Field Ration", "quantity": 1},
        ],
        "balance_summary": {
            "capped_turn_counts": {"hunger": 0, "thirst": 0, "fatigue": 0},
            "longest_capped_streaks": {"hunger": 0, "thirst": 0, "fatigue": 0},
            "thirst_balance_attention": False,
        },
        "runtime_probe_summary": {"probe_rows": 100, "override_applied_rows": 3},
    }
    return {
        "ok": True,
        "requested_turns": 100,
        "turns_executed": 100,
        "passed_gate_count": 31,
        "failed_gate_count": 0,
        "artifact_level_summaries": {"survival-pressure-relief-summary.json": survival_pressure},
    }


def _readiness():
    return {
        "ok": True,
        "failed_gates": [],
        "gates": {
            "survival_autoplay_evidence_ok": True,
            "survival_response_ok": True,
            "survival_metric_source_ok": True,
        },
    }


def test_n128_survival_exit_criteria_passes_on_green_survival_artifact() -> None:
    summary = build_survival_exit_criteria_summary(_evaluation(), _readiness())

    assert summary["ok"] is True
    assert summary["failed_checks"] == []
    assert summary["drink_water_count"] == 4
    assert summary["eat_food_count"] == 2
    assert summary["blocked_relief_count"] == 0
    assert summary["capped_thirst_turns"] == 0
    assert summary["emergency_water_count"] == 3


def test_n128_survival_exit_criteria_reports_regressions() -> None:
    evaluation = _evaluation()
    pressure = evaluation["artifact_level_summaries"]["survival-pressure-relief-summary.json"]
    pressure["relief_counts_by_kind"] = {"drink_water": 1}
    pressure["blocked_relief_count"] = 2
    pressure["balance_summary"]["capped_turn_counts"]["thirst"] = 8
    pressure["balance_summary"]["longest_capped_streaks"]["thirst"] = 4

    summary = build_survival_exit_criteria_summary(evaluation, _readiness())

    assert summary["ok"] is False
    assert "blocked_relief_count_ok" in summary["failed_checks"]
    assert "drink_water_count_ok" in summary["failed_checks"]
    assert "thirst_capped_turns_ok" in summary["failed_checks"]


def test_n129_payload_budget_flags_oversized_rows() -> None:
    transcript = [
        {"turn_index": 1, "player_action": "look", "turn_contract": {"ok": True}},
        {"turn_index": 2, "player_reasoning_plan": "x" * 2000, "small": True},
    ]

    summary = build_transcript_payload_budget_summary(
        transcript,
        max_compact_row_bytes=1000,
        max_projected_1000_bytes=1_000_000,
    )

    assert summary["ok"] is False
    assert summary["oversized_row_count"] == 1
    assert summary["oversized_rows_sample"][0]["turn_index"] == 2
    assert any(item["field"] == "player_reasoning_plan" for item in summary["heavy_field_totals"])


def test_bundle_a_writes_expected_artifacts(tmp_path) -> None:
    result_dir = tmp_path / "autoplay-campaign-results-unzipped"
    result_dir.mkdir()
    (result_dir / "hundred-turn-evaluation.json").write_text(json.dumps(_evaluation()), encoding="utf-8")
    (result_dir / "hundred-turn-readiness-summary.json").write_text(json.dumps(_readiness()), encoding="utf-8")
    (result_dir / "autoplay-health.json").write_text(json.dumps({"ok": False, "hundred_turn_evaluation_ok": True, "hundred_turn_readiness_ok": True, "warnings": ["quality_gate_summary_failed"]}), encoding="utf-8")
    (result_dir / "full-transcript.json").write_text(json.dumps([{"turn_index": 1, "player_action": "look"}]), encoding="utf-8")

    quality = repair_quality_gate_artifacts(result_dir)
    bundle = write_bundle_a_artifacts(result_dir)

    assert quality["applied"] is True
    assert bundle["applied"] is True
    assert (result_dir / "quality-gate-summary.json").exists()
    assert (result_dir / "survival-exit-criteria-summary.json").exists()
    assert (result_dir / "transcript-payload-budget-summary.json").exists()
    health = json.loads((result_dir / "autoplay-health.json").read_text(encoding="utf-8"))
    assert health["ok"] is True
    assert health["quality_gate_summary_path"] == "quality-gate-summary.json"
