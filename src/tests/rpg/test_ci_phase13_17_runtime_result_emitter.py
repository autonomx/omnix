import json
import sys
from pathlib import Path

from app.rpg.autoplay_performance_artifacts import build_autoplay_performance_summary
from tests.rpg.autoplay import runtime_turn_result_capture_hook as capture
from tests.rpg.autoplay.live_performance_bridge import append_live_performance_bridge_row
from tests.rpg.autoplay.result_path_diagnostics import (
    RUNTIME_TURN_RESULTS_NAME,
    collect_result_path_diagnostics,
    extract_result_path_events,
)
from tests.rpg.autoplay.runtime_turn_result_capture_hook import (
    ARTIFACT_NAME,
    backfill_runtime_turn_results_from_console_log,
    install_runtime_turn_result_capture_hook,
    parse_console_log_runtime_turn_results,
    parse_runtime_turn_result_line,
)
from tests.rpg.autoplay.survival_report_writer_hook import (
    load_runtime_turn_result_rows,
    run_autoplay_survival_report_writer_hook,
)


def test_phase13_17_parse_runtime_turn_result_line_extracts_keys():
    line = (
        "[AUTOPLAY-PROBE] event=runtime_turn_execution.result turn=59 ok=False "
        "keys=manual_harness_trace,manual_stage_trace,provider_trace,runtime_name,turn_contract,turn_perf_trace_summary"
    )

    event = parse_runtime_turn_result_line(line)

    assert event["runtime_result"] is True
    assert event["event_class"] == "runtime_result_emission"
    assert event["ok"] is False
    assert event["turn_index"] == 59
    assert "turn_perf_trace_summary" in event["trace_keys_present"]
    assert "runtime_name" in event["result_keys"]


def test_phase13_17_capture_stream_writes_runtime_turn_results(tmp_path: Path):
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    try:
        capture._INSTALLED = False
        install_runtime_turn_result_capture_hook(output_dir=tmp_path)
        print(
            "[AUTOPLAY-PROBE] event=runtime_turn_execution.result turn_index=60 ok=False "
            "keys=manual_harness_trace,runtime_name,turn_perf_trace_summary"
        )
        sys.stdout.flush()
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        capture._INSTALLED = False

    payload = json.loads((tmp_path / ARTIFACT_NAME).read_text(encoding="utf-8"))
    assert payload["event_count"] == 1
    assert payload["events"][0]["turn_index"] == 60
    assert "runtime_name" in payload["events"][0]["trace_keys_present"]


def test_phase13_17_source_text_alone_no_longer_marks_runtime_result():
    events = extract_result_path_events(
        {
            "ok": False,
            "source": "final_transcript_rows.turn_contract.runtime_survival_evidence",
            "error_type": "SoftClassification",
        },
        source_path="summary.json",
    )

    assert events
    assert events[0]["runtime_result"] is False
    assert events[0]["event_class"] == "generic_failure"


def test_phase13_17_runtime_emission_events_feed_runtime_result_events(tmp_path: Path):
    payload = {
        "events": [
            parse_runtime_turn_result_line(
                "event=runtime_turn_execution.result turn=61 ok=False "
                "keys=manual_stage_trace,runtime_name,turn_perf_trace_summary"
            )
        ]
    }
    (tmp_path / RUNTIME_TURN_RESULTS_NAME).write_text(json.dumps(payload), encoding="utf-8")

    result = collect_result_path_diagnostics(tmp_path)

    assert result["runtime_result_event_count"] >= 1
    event = result["runtime_result_events"][0]
    assert event["event_class"] == "runtime_result_emission"
    assert event["turn_index"] == 61
    assert "turn_perf_trace_summary" in event["trace_keys_present"]


def test_phase13_17_runtime_emission_rows_bridge_into_performance_summary(tmp_path: Path):
    payload = {
        "events": [
            parse_runtime_turn_result_line(
                "event=runtime_turn_execution.result turn=62 ok=False "
                "keys=manual_stage_trace,runtime_name,turn_perf_trace_summary"
            )
        ]
    }
    (tmp_path / RUNTIME_TURN_RESULTS_NAME).write_text(json.dumps(payload), encoding="utf-8")

    rows = load_runtime_turn_result_rows(tmp_path)
    bridged = append_live_performance_bridge_row(rows, {})
    summary = build_autoplay_performance_summary(bridged)
    bridge = summary["manual_turn_breakdown"]["turn_metrics"][-1]

    assert rows
    assert bridge["turn_index"] == -1
    assert summary["manual_turn_breakdown"]["turns_observed"] >= 1


def test_phase13_17_post_run_hook_reports_runtime_result_rows(tmp_path: Path):
    (tmp_path / RUNTIME_TURN_RESULTS_NAME).write_text(
        json.dumps(
            {
                "events": [
                    parse_runtime_turn_result_line(
                        "event=runtime_turn_execution.result turn=63 ok=False "
                        "keys=manual_harness_trace,runtime_name,turn_perf_trace_summary"
                    )
                ]
            }
        ),
        encoding="utf-8",
    )

    result = run_autoplay_survival_report_writer_hook(
        script_path=Path("src/tests/rpg/autoplay_llm_campaign.py"),
        results_dir=tmp_path,
    )

    assert result["ok"] is True
    assert result["runtime_turn_result_rows_observed"] == 1
    assert result["result_path_diagnostics"]["runtime_result_event_count"] >= 1


def test_phase13_18_console_log_parser_reads_runtime_probe_lines(tmp_path: Path):
    console = tmp_path / "console-log.txt"
    console.write_text(
        "noise\n"
        "[AUTOPLAY-PROBE] ts=2026-06-07T01:02:03 event=runtime_turn_execution.result turn_index=64 ok=False "
        "keys=manual_harness_trace,manual_harness_trace_summary,manual_stage_trace,runtime_name,turn_perf_trace_summary\n",
        encoding="utf-8",
    )

    events = parse_console_log_runtime_turn_results(console)

    assert len(events) == 1
    assert events[0]["capture_source"] == "console_log"
    assert events[0]["timestamp"] == "2026-06-07T01:02:03"
    assert events[0]["turn_index"] == 64
    assert "manual_harness_trace_summary" in events[0]["trace_keys_present"]


def test_phase13_18_backfills_runtime_turn_results_from_console_log(tmp_path: Path):
    (tmp_path / "console-log.txt").write_text(
        "[AUTOPLAY-PROBE] event=runtime_turn_execution.result turn=65 ok=False "
        "keys=manual_stage_trace,runtime_name,turn_perf_trace_summary\n",
        encoding="utf-8",
    )

    result = backfill_runtime_turn_results_from_console_log(tmp_path)

    assert result["event_count"] == 1
    assert result["backfilled_from_console_log"] is True
    assert (tmp_path / ARTIFACT_NAME).exists()


def test_phase13_18_post_run_hook_backfills_before_diagnostics(tmp_path: Path):
    (tmp_path / "console-log.txt").write_text(
        "[AUTOPLAY-PROBE] event=runtime_turn_execution.result turn=66 ok=False "
        "keys=manual_harness_trace,runtime_name,turn_perf_trace_summary\n",
        encoding="utf-8",
    )

    result = run_autoplay_survival_report_writer_hook(
        script_path=Path("src/tests/rpg/autoplay_llm_campaign.py"),
        results_dir=tmp_path,
    )

    assert result["ok"] is True
    assert result["runtime_turn_result_backfill"]["event_count"] == 1
    assert result["runtime_turn_result_rows_observed"] == 1
    assert result["result_path_diagnostics"]["runtime_result_event_count"] >= 1
    assert (tmp_path / ARTIFACT_NAME).exists()
