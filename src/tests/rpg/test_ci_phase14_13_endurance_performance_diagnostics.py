from __future__ import annotations

import json
from pathlib import Path

from tests.rpg import interactive_cli_live_llm_endurance_matrix as endurance
from tests.rpg.interactive_cli_live_quality_eval import LIVE_QUALITY_EVAL_VERSION


def _transcript(text: str = "provider narration") -> dict:
    return {"turns": [{"turn_index": 1, "player_input": "test", "raw_narration": text, "narration_source": "provider_runtime_narration"}]}


def _judge_all_ok(**kwargs) -> dict:
    return {
        "ok": True,
        "requirements": {
            name: {"ok": True, "evidence": f"visible evidence for {name}", "reason": "satisfied"}
            for name in kwargs["requirements"]
        },
        "reason": "all requirements satisfied",
    }


def _quality(turn_count: int = 25) -> dict:
    return {
        "format_version": LIVE_QUALITY_EVAL_VERSION,
        "ok": True,
        "turn_count": turn_count,
        "avg_score": 4.0,
        "scores": {"coherence": 4.0, "agency": 4.0, "specificity": 4.0, "continuity": 4.0, "fun": 4.0},
        "failures": [],
        "warnings": [],
        "signals": {"llm_narration_ratio": 1.0, "visible_repair_turn_ratio": 0.0},
    }


def _performance(completed_turns: int = 25, p95: float = 14.5) -> dict:
    return {
        "format_version": "interactive_cli_performance_v2",
        "completed_turns": completed_turns,
        "elapsed_seconds": 340.0,
        "avg_turn_seconds": 13.6,
        "p50_turn_seconds": 13.4,
        "p95_turn_seconds": p95,
        "max_turn_seconds": 15.2,
        "slow_turn_threshold_seconds": 10.0,
        "slow_turn_count": completed_turns,
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
        "slow_turns": [{"turn_index": 1, "runtime_apply_turn_seconds": 10.4, "turn_total_seconds": 13.6}],
    }


def test_phase14_13_performance_diagnostics_extracts_budget_fields() -> None:
    result = endurance.evaluate_live_endurance_performance(_performance(), p95_warning_threshold_seconds=10.0)

    assert result["format_version"] == endurance.LIVE_ENDURANCE_PERFORMANCE_VERSION
    assert result["ok"] is True
    assert result["completed_turns"] == 25
    assert result["avg_turn_seconds"] == 13.6
    assert result["p95_turn_seconds"] == 14.5
    assert result["slow_turn_ratio"] == 1.0
    assert result["dominant_phase"] == "runtime_apply_turn_seconds"
    assert result["runtime_apply_avg_seconds"] == 10.4
    assert result["runtime_narration_contract_avg_seconds"] == 3.1
    assert result["slow_turn_bucket_counts"] == {"runtime_apply_turn_seconds": 25}
    assert "live_endurance_p95_turn_seconds_over_budget" in result["warnings"]


def test_phase14_13_performance_warning_is_diagnostic_not_failure() -> None:
    quality = endurance.apply_endurance_performance_to_quality(_quality(), endurance.evaluate_live_endurance_performance(_performance(), p95_warning_threshold_seconds=10.0))

    assert quality["ok"] is True
    assert "live_endurance_performance" in quality
    assert quality["signals"]["live_endurance_p95_turn_seconds"] == 14.5
    assert quality["signals"]["live_endurance_dominant_phase"] == "runtime_apply_turn_seconds"
    assert "live_endurance_p95_turn_seconds_over_budget" in quality["warnings"]


def test_phase14_13_matrix_aggregates_performance_diagnostics(tmp_path: Path) -> None:
    captured: list[dict] = []

    def fake_runner(**kwargs):
        captured.append(dict(kwargs))
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = output_dir / "interactive-transcript.json"
        transcript_path.write_text(json.dumps(_transcript()), encoding="utf-8")
        performance_path = output_dir / "interactive-performance.json"
        performance_path.write_text(json.dumps(_performance(completed_turns=len(kwargs["commands"]))), encoding="utf-8")
        summary_path = Path(kwargs["summary_path"])
        summary_path.write_text(json.dumps(_quality(turn_count=len(kwargs["commands"]))), encoding="utf-8")
        return {
            "ok": True,
            "skipped": False,
            "transcript_path": str(transcript_path),
            "performance_path": str(performance_path),
            "quality_summary_path": str(summary_path),
            "quality": _quality(turn_count=len(kwargs["commands"])),
        }

    result = endurance.run_live_endurance_matrix(
        packs=["combat-travel-aftermath-25"],
        allow_live=True,
        output_dir=tmp_path / "endurance",
        playtest_runner=fake_runner,
        semantic_judge_func=_judge_all_ok,
        p95_warning_threshold_seconds=10.0,
    )

    assert result["ok"] is True
    aggregate = result["aggregate"]
    assert aggregate["live_endurance_performance"]["pack_count"] == 1
    assert aggregate["live_endurance_performance"]["completed_turns"] == 25
    assert aggregate["live_endurance_performance"]["p95_turn_seconds_max"] == 14.5
    assert aggregate["live_endurance_performance"]["dominant_phase"] == "runtime_apply_turn_seconds"
    assert aggregate["performance_warning_count"] == 1
    summary = json.loads(Path(result["summary_paths"][0]).read_text(encoding="utf-8"))
    assert summary["ok"] is True
    assert summary["live_endurance_performance"]["p95_turn_seconds"] == 14.5
    assert summary["signals"]["live_endurance_runtime_apply_avg_seconds"] == 10.4
    assert "live_endurance_p95_turn_seconds_over_budget" in summary["warnings"]
    assert captured[0]["scenario_pack"] == ""
