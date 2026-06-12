from __future__ import annotations

import json
from pathlib import Path

from tests.rpg import interactive_cli_live_llm_apply_turn_diagnostics as diagnostics


def _performance(*, completed_turns: int = 25) -> dict:
    return {
        "format_version": "interactive_cli_performance_v2",
        "completed_turns": completed_turns,
        "elapsed_seconds": 340.0,
        "avg_turn_seconds": 13.6,
        "p95_turn_seconds": 14.5,
        "max_turn_seconds": 15.2,
        "slow_turn_threshold_seconds": 10.0,
        "slow_turn_count": 2,
        "phase_avg_seconds": {
            "runtime_apply_turn_seconds": 10.4,
            "runtime_narration_contract_seconds": 3.1,
            "turn_total_seconds": 13.6,
        },
        "phase_totals_seconds": {
            "runtime_apply_turn_seconds": 260.0,
            "runtime_narration_contract_seconds": 77.5,
            "turn_total_seconds": 340.0,
        },
        "slow_turns": [
            {
                "turn_index": 3,
                "player_input": "I ask Bran what he remembers.",
                "runtime_apply_turn_seconds": 11.2,
                "turn_total_seconds": 14.1,
                "manual_harness_slowest_stages": [
                    {"event": "provider_generate_narration", "elapsed_seconds": 7.25},
                    {"event": "session_state_load", "elapsed_seconds": 1.5},
                    {"event": "simulation_apply_turn", "elapsed_seconds": 0.75},
                ],
            },
            {
                "turn_index": 4,
                "player_input": "I check the route back.",
                "runtime_apply_turn_seconds": 10.8,
                "turn_total_seconds": 13.7,
                "manual_harness_slowest_stages": [
                    {"event": "provider_generate_narration", "elapsed_seconds": 6.75},
                    {"event": "quest_memory_lookup", "elapsed_seconds": 1.25},
                ],
            },
        ],
    }


def test_phase14_14_categorizes_apply_turn_stage_events() -> None:
    assert diagnostics.categorize_apply_turn_stage("provider_generate_narration") == "provider_or_llm"
    assert diagnostics.categorize_apply_turn_stage("session_state_load") == "session_state_io"
    assert diagnostics.categorize_apply_turn_stage("simulation_apply_turn") == "simulation_apply"
    assert diagnostics.categorize_apply_turn_stage("quest_memory_lookup") == "world_memory_or_quest"


def test_phase14_14_aggregates_apply_turn_hotspots_and_updates_aggregate(tmp_path: Path) -> None:
    output_dir = tmp_path / "live-llm-endurance-matrix"
    pack_dir = output_dir / "01-companion-quest-economy-25"
    pack_dir.mkdir(parents=True)
    (pack_dir / "interactive-performance.json").write_text(json.dumps(_performance()), encoding="utf-8")
    aggregate_path = output_dir / "live-quality-aggregate.json"
    aggregate_path.write_text(json.dumps({"format_version": "live_quality_eval_aggregate_v1", "ok": True}), encoding="utf-8")

    result = diagnostics.diagnose_live_endurance_apply_turns(output_dir=output_dir)

    assert result["format_version"] == diagnostics.LIVE_ENDURANCE_APPLY_TURN_DIAGNOSTICS_VERSION
    assert result["ok"] is True
    assert result["pack_count"] == 1
    assert result["completed_turns"] == 25
    assert result["slow_turn_count"] == 2
    assert result["runtime_apply_total_seconds"] == 260.0
    assert result["sampled_stage_total_seconds"] == 17.5
    assert result["sampled_stage_share_of_runtime_apply"] == round(17.5 / 260.0, 4)
    assert result["top_apply_turn_events"][0]["name"] == "provider_generate_narration"
    assert result["top_apply_turn_events"][0]["category"] == "provider_or_llm"
    assert result["top_apply_turn_events"][0]["count"] == 2
    assert result["top_apply_turn_categories"][0]["name"] == "provider_or_llm"

    diagnostics_path = output_dir / "live-endurance-apply-turn-diagnostics.json"
    assert diagnostics_path.exists()
    written = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    assert written["top_apply_turn_events"][0]["total_seconds"] == 14.0

    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    assert aggregate["ok"] is True
    assert aggregate["live_endurance_apply_turn_diagnostics"]["pack_count"] == 1
    assert aggregate["apply_turn_diagnostics_warning_count"] == 0


def test_phase14_14_warns_when_slow_turns_have_no_stage_samples(tmp_path: Path) -> None:
    output_dir = tmp_path / "live-llm-endurance-matrix"
    pack_dir = output_dir / "01-combat-travel-aftermath-25"
    pack_dir.mkdir(parents=True)
    perf = _performance()
    perf["slow_turns"] = [{"turn_index": 1, "manual_harness_slowest_stages": []}]
    (pack_dir / "interactive-performance.json").write_text(json.dumps(perf), encoding="utf-8")

    result = diagnostics.diagnose_live_endurance_apply_turns(output_dir=output_dir, update_aggregate=False)

    assert result["ok"] is True
    assert "live_endurance_apply_turn_no_manual_stage_samples:combat-travel-aftermath-25" in result["warnings"]
    assert result["top_apply_turn_events"] == []


def test_phase14_14_status_marker_reports_top_event() -> None:
    marker = diagnostics.render_apply_turn_diagnostics_status_marker(
        {
            "ok": True,
            "pack_count": 1,
            "slow_turn_count": 2,
            "sampled_stage_share_of_runtime_apply": 0.1234,
            "top_apply_turn_events": [{"name": "provider_generate_narration", "total_seconds": 14.0}],
        }
    )

    assert "ok=true" in marker
    assert "pack_count=1" in marker
    assert "top_event=provider_generate_narration" in marker
