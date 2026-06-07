import json
import zipfile
from pathlib import Path

from app.rpg.autoplay_performance_artifacts import build_autoplay_performance_summary
from tests.rpg.autoplay.live_performance_bridge import append_live_performance_bridge_row
from tests.rpg.autoplay.result_path_diagnostics import (
    SUMMARY_NAME,
    extract_result_path_events,
    write_result_path_diagnostics,
)
from tests.rpg.autoplay.survival_report_writer_hook import run_autoplay_survival_report_writer_hook


def test_phase13_15_extracts_failed_result_with_traces():
    payload = {
        "turns": [
            {
                "turn_index": 59,
                "ok": False,
                "error_type": "RuntimeFailure",
                "error": "bounded test failure",
                "runtime_name": "runtime_turn_execution",
                "player_input": "continue",
                "manual_harness_trace": [{"stage": "manual", "duration_ms": 10}],
                "turn_perf_trace_summary": {"manual_turn_ms": {"avg_ms": 12000, "count": 1}},
            }
        ]
    }

    events = extract_result_path_events(payload, source_path="artifact.json")

    assert len(events) == 1
    event = events[0]
    assert event["turn_index"] == 59
    assert event["error_fields"]["error_type"] == "RuntimeFailure"
    assert "manual_harness_trace" in event["trace_keys_present"]
    assert "turn_perf_trace_summary" in event["trace_keys_present"]


def test_phase13_15_writes_result_path_diagnostics_from_files_and_zip(tmp_path: Path):
    (tmp_path / "rows.json").write_text(
        json.dumps({"turns": [{"turn_index": 60, "ok": False, "error_type": "ValueError", "message": "bad"}]}),
        encoding="utf-8",
    )
    zip_path = tmp_path / "autoplay-campaign-results.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(
            "nested.json",
            json.dumps({"turns": [{"turn_index": 61, "ok": False, "exception_type": "RuntimeFailure", "message": "nested"}]}),
        )

    result = write_result_path_diagnostics(tmp_path, zip_path=zip_path)

    assert result["ok"] is True
    assert result["event_count"] >= 2
    assert (tmp_path / SUMMARY_NAME).exists()


def test_phase13_15_trace_summary_bridge_populates_manual_timing():
    rows = [
        {
            "turn_index": 1,
            "turn_result": {
                "turn_perf_trace_summary": {
                    "manual_turn_ms": {"avg_ms": 12500, "count": 100, "max_ms": 15000},
                    "state_bounds_ms": {"avg_ms": 5, "count": 100, "max_ms": 9},
                    "background_enqueue_ms": {"avg_ms": 7, "count": 100, "max_ms": 12},
                }
            },
        }
    ]

    bridged = append_live_performance_bridge_row(rows, {})
    summary = build_autoplay_performance_summary(bridged)
    breakdown = summary["manual_turn_breakdown"]["summary"]

    assert breakdown["manual_turn_ms"]["avg_ms"] == 12500
    assert breakdown["state_snapshot_ms"]["avg_ms"] == 5
    assert breakdown["deferred_enqueue_ms"]["avg_ms"] == 7


def test_phase13_15_post_run_hook_writes_result_path_artifact(tmp_path: Path):
    (tmp_path / "autoplay-performance.json").write_text(json.dumps({"stage_summary": {}}), encoding="utf-8")
    (tmp_path / "turns.json").write_text(
        json.dumps({"turns": [{"turn_index": 62, "ok": False, "error_type": "RuntimeFailure", "error": "depth"}]}),
        encoding="utf-8",
    )

    result = run_autoplay_survival_report_writer_hook(
        script_path=Path("src/tests/rpg/autoplay_llm_campaign.py"),
        results_dir=tmp_path,
    )

    assert result["ok"] is True
    assert result["result_path_diagnostics"]["event_count"] >= 1
    assert (tmp_path / SUMMARY_NAME).exists()
