from __future__ import annotations

import json

from app.rpg.session.bundle_c_artifacts import (
    build_economy_resource_pressure_summary,
    build_npc_agency_schedule_summary,
    write_bundle_c_artifacts,
)


def _evaluation():
    return {
        "ok": True,
        "gates": {
            "npc_agency_present": {
                "ok": True,
                "value": {
                    "event_count": 182,
                    "direct_graph_agency_count": 182,
                    "npc_count": 3,
                    "schedule_event_count": 32,
                    "agency_event_count": 0,
                    "memory_event_count": 182,
                },
            },
            "economy_pressure_present": {
                "ok": True,
                "value": {
                    "event_count": 12,
                    "paid_count": 12,
                    "unpaid_count": 0,
                    "warning_count": 3,
                    "ending_currency": {"gold": 3, "silver": 0, "copper": 5},
                    "total_spent": {"gold": 7, "copper": 25},
                },
            },
            "world_signal_summary_present": {
                "ok": True,
                "value": {"world_signal_count": 5, "by_kind": {"economy_pressure": 5}},
            },
            "world_state_compression_active": {"ok": True, "value": {}},
        },
        "artifact_level_summaries": {},
    }


def _readiness():
    return {"ok": True, "failed_gates": []}


def test_n132_npc_agency_schedule_summary_passes_for_green_evidence() -> None:
    summary = build_npc_agency_schedule_summary(_evaluation(), _readiness())

    assert summary["ok"] is True
    assert summary["failed_checks"] == []
    assert summary["npc_count"] == 3
    assert summary["schedule_event_count"] == 32
    assert summary["memory_event_count"] == 182
    assert summary["advisory_ok"] is True


def test_n132_npc_agency_schedule_summary_flags_missing_schedule() -> None:
    evaluation = _evaluation()
    evaluation["gates"]["npc_agency_present"]["value"]["schedule_event_count"] = 0

    summary = build_npc_agency_schedule_summary(evaluation, _readiness())

    assert summary["ok"] is False
    assert "schedule_events_ok" in summary["failed_checks"]


def test_n133_economy_resource_pressure_summary_passes_for_green_evidence() -> None:
    summary = build_economy_resource_pressure_summary(_evaluation(), _readiness())

    assert summary["ok"] is True
    assert summary["paid_count"] == 12
    assert summary["unpaid_count"] == 0
    assert summary["economy_world_signal_count"] == 5
    assert summary["total_spent"] == {"gold": 7, "copper": 25}


def test_n133_economy_resource_pressure_summary_flags_missing_spend() -> None:
    evaluation = _evaluation()
    evaluation["gates"]["economy_pressure_present"]["value"]["total_spent"] = {}

    summary = build_economy_resource_pressure_summary(evaluation, _readiness())

    assert summary["ok"] is False
    assert "spend_recorded_ok" in summary["failed_checks"]


def test_bundle_c_writes_expected_artifacts_and_patches_health(tmp_path) -> None:
    result_dir = tmp_path / "autoplay-campaign-results-unzipped"
    result_dir.mkdir()
    (result_dir / "hundred-turn-evaluation.json").write_text(json.dumps(_evaluation()), encoding="utf-8")
    (result_dir / "hundred-turn-readiness-summary.json").write_text(json.dumps(_readiness()), encoding="utf-8")
    (result_dir / "autoplay-health.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (result_dir / "artifact-manifest.json").write_text(json.dumps({"ok": True, "files": [], "embedded_artifacts": {}}), encoding="utf-8")

    result = write_bundle_c_artifacts(result_dir)

    assert result["applied"] is True
    assert result["npc_agency_schedule_ok"] is True
    assert result["economy_resource_pressure_ok"] is True
    assert (result_dir / "npc-agency-schedule-summary.json").exists()
    assert (result_dir / "economy-resource-pressure-summary.json").exists()

    manifest = json.loads((result_dir / "artifact-manifest.json").read_text(encoding="utf-8"))
    assert "npc-agency-schedule-summary.json" in manifest["bundle_c_files"]
    assert "economy-resource-pressure-summary.json" in manifest["bundle_c_files"]
    assert manifest["embedded_artifacts"]["npc-agency-schedule-summary.json"]["ok"] is True
    assert manifest["embedded_artifacts"]["economy-resource-pressure-summary.json"]["ok"] is True

    health = json.loads((result_dir / "autoplay-health.json").read_text(encoding="utf-8"))
    assert health["bundle_c_artifacts_ok"] is True
    assert health["npc_agency_schedule_ok"] is True
    assert health["economy_resource_pressure_ok"] is True

    evaluation = json.loads((result_dir / "hundred-turn-evaluation.json").read_text(encoding="utf-8"))
    assert evaluation["bundle_c_artifacts"]["npc_agency_schedule_ok"] is True
    assert evaluation["artifact_level_summaries"]["economy-resource-pressure-summary.json"]["ok"] is True
