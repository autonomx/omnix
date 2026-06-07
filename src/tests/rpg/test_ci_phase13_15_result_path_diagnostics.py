import json
import zipfile
from pathlib import Path

from app.rpg.autoplay_performance_artifacts import build_autoplay_performance_summary
from tests.rpg.autoplay.live_performance_bridge import append_live_performance_bridge_row
from tests.rpg.autoplay.result_path_diagnostics import (
    SUMMARY_NAME,
    extract_result_path_events,
    split_result_path_events,
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
    assert event["runtime_result"] is True
    assert event["event_class"] == "runtime_result"
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
    assert "runtime_result_events" in result
    assert "generic_failure_events" in result
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


def test_phase13_16_runtime_events_are_split_and_prioritized():
    generic_events = [
        {
            "turn_index": index,
            "json_path": f"$.generic[{index}]",
            "source_path": "generic.json",
            "runtime_result": False,
            "event_class": "generic_failure",
            "trace_keys_present": [],
        }
        for index in range(320)
    ]
    runtime_event = {
        "turn_index": 59,
        "json_path": "$.runtime.turns[59]",
        "source_path": "transcript.json",
        "runtime_result": True,
        "event_class": "runtime_result",
        "trace_keys_present": ["manual_stage_trace", "turn_perf_trace_summary", "runtime_name"],
    }

    split = split_result_path_events([*generic_events, runtime_event])

    assert split["runtime_result_events"][0]["json_path"] == "$.runtime.turns[59]"
    assert len(split["generic_failure_events"]) == 300


def test_phase13_16_collect_keeps_runtime_event_when_generic_noise_exceeds_cap(tmp_path: Path):
    generic = {"items": [{"turn_index": index, "ok": False, "error_type": "SoftGate"} for index in range(330)]}
    runtime_payload = {
        "turns": [
            {
                "turn_index": 59,
                "ok": False,
                "runtime_name": "runtime_turn_execution",
                "manual_stage_trace": [{"stage": "runtime", "duration_ms": 1}],
                "turn_perf_trace_summary": {"manual_turn_ms": {"avg_ms": 1, "count": 1}},
            }
        ]
    }
    (tmp_path / "generic-noise.json").write_text(json.dumps(generic), encoding="utf-8")
    (tmp_path / "transcript.json").write_text(json.dumps(runtime_payload), encoding="utf-8")

    result = write_result_path_diagnostics(tmp_path)

    assert result["runtime_result_event_count"] == 1
    assert result["runtime_result_events"][0]["turn_index"] == 59
    assert result["generic_failure_event_count"] == 300
