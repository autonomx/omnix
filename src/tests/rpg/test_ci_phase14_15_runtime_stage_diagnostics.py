from __future__ import annotations

import json
from pathlib import Path

from tests.rpg.interactive_cli_live_llm_runtime_stage_diagnostics import (
    diagnose_live_endurance_runtime_stages,
    render_runtime_stage_diagnostics_status_marker,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_runtime_stage_diagnostics_aggregates_embedded_stage_timing(tmp_path: Path) -> None:
    out = tmp_path / "live-llm-endurance-matrix"
    pack_dir = out / "01-companion-quest-economy-25"
    _write_json(
        pack_dir / "interactive-transcript.json",
        {
            "turns": [
                {
                    "turn_index": 1,
                    "player_input": "I ask Bran to travel with me.",
                    "interactive_cli_performance": {"runtime_apply_turn_seconds": 1.0},
                    "raw_result": {
                        "manual_turn_stage_timing": {
                            "manual_turn_timing_source": "interactive_first_call_runtime_v1",
                            "pre_runtime_intent_llm_ms": 700.0,
                            "deterministic_runtime_apply_ms": 250.0,
                            "grounding_validation_ms": 25.0,
                            "repair_ms": 5.0,
                            "state_snapshot_ms": 10.0,
                            "deferred_enqueue_ms": 1.0,
                        }
                    },
                },
                {
                    "turn_index": 2,
                    "player_input": "I check the route.",
                    "interactive_cli_performance": {"runtime_apply_turn_seconds": 2.0},
                    "raw_result": {
                        "result": {
                            "manual_turn_stage_timing": {
                                "pre_runtime_intent_llm_ms": 1000.0,
                                "deterministic_runtime_apply_ms": 800.0,
                                "grounding_validation_ms": 50.0,
                                "repair_ms": 0.0,
                                "state_snapshot_ms": 20.0,
                                "deferred_enqueue_ms": 2.0,
                            }
                        }
                    },
                },
            ]
        },
    )
    _write_json(
        pack_dir / "interactive-performance.json",
        {"completed_turns": 2, "phase_totals_seconds": {"runtime_apply_turn_seconds": 3.0}},
    )
    _write_json(out / "live-quality-aggregate.json", {"ok": True})

    result = diagnose_live_endurance_runtime_stages(output_dir=out)

    assert result["ok"] is True
    assert result["pack_count"] == 1
    assert result["completed_turns"] == 2
    assert result["turns_with_runtime_stage_timing"] == 2
    assert result["runtime_apply_total_seconds"] == 3.0
    assert result["runtime_embedded_stage_total_seconds"] == 2.863
    assert result["runtime_embedded_stage_share_of_apply"] == 0.9543
    assert result["top_runtime_stages"][0]["name"] == "pre_runtime_intent_llm_ms"
    assert result["top_runtime_stages"][0]["total_seconds"] == 1.7
    assert (out / "live-endurance-runtime-stage-diagnostics.json").exists()

    aggregate = json.loads((out / "live-quality-aggregate.json").read_text(encoding="utf-8"))
    assert aggregate["ok"] is True
    assert aggregate["live_endurance_runtime_stage_diagnostics"]["turns_with_runtime_stage_timing"] == 2
    assert aggregate["runtime_stage_diagnostics_warning_count"] == 0


def test_runtime_stage_diagnostics_warns_when_transcript_has_no_embedded_timing(tmp_path: Path) -> None:
    out = tmp_path / "live-llm-endurance-matrix"
    pack_dir = out / "01-memory-social-world-25"
    _write_json(pack_dir / "interactive-transcript.json", {"turns": [{"turn_index": 1, "player_input": "hello"}]})
    _write_json(pack_dir / "interactive-performance.json", {"phase_totals_seconds": {"runtime_apply_turn_seconds": 4.0}})

    result = diagnose_live_endurance_runtime_stages(output_dir=out, update_aggregate=False)

    assert result["ok"] is True
    assert result["turns_with_runtime_stage_timing"] == 0
    assert result["warnings"] == ["live_endurance_runtime_stage_no_embedded_timing:memory-social-world-25"]
    marker = render_runtime_stage_diagnostics_status_marker(result)
    assert "RPG_LIVE_ENDURANCE_RUNTIME_STAGE_DIAGNOSTICS" in marker
    assert "turns_with_timing=0" in marker
