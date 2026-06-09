import json
from pathlib import Path

from tests.rpg.autoplay import runtime_turn_result_capture_hook as hook


def test_phase13_35_stream_turn_error_line_uses_default_output_dir(tmp_path: Path, monkeypatch):
    original_output_dir = hook._OUTPUT_DIR
    monkeypatch.chdir(tmp_path)
    try:
        hook._OUTPUT_DIR = None
        hook.record_stream_turn_error_line("[2026-01-01T00:00:00] TURN 59 " + hook._EVENT_WORD + ": ValueError: boom")
    finally:
        hook._OUTPUT_DIR = original_output_dir

    path = tmp_path.joinpath(*hook._DEFAULT_AUTOPLAY_RESULT_DIR_PARTS) / hook.TURN_ERROR_ARTIFACT_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["source"] == hook.SOURCE
    assert payload["event_count"] == 1
    event = payload["events"][0]
    assert event["event_class"] == "stream_turn_failure_line"
    assert event["capture_source"] == "stream"
    assert event["turn_index"] == 59
    assert event["error_type"] == "ValueError"
    assert event["message"] == "boom"
    assert event["stack_tail"]


def test_phase13_35_runtime_result_line_uses_default_output_dir(tmp_path: Path, monkeypatch):
    original_output_dir = hook._OUTPUT_DIR
    monkeypatch.chdir(tmp_path)
    try:
        hook._OUTPUT_DIR = None
        hook.record_runtime_turn_result_line(
            "[AUTOPLAY-PROBE] ts=2026-01-01T00:00:01 event=runtime_turn_execution.result "
            "thread=MainThread turn_index=60 ok=False keys=manual_stage_trace,turn_perf_trace"
        )
    finally:
        hook._OUTPUT_DIR = original_output_dir

    path = tmp_path.joinpath(*hook._DEFAULT_AUTOPLAY_RESULT_DIR_PARTS) / hook.ARTIFACT_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["source"] == hook.SOURCE
    assert payload["event_count"] == 1
    event = payload["events"][0]
    assert event["capture_source"] == "stream"
    assert event["turn_index"] == 60
    assert event["ok"] is False
    assert event["trace_keys_present"] == ["manual_stage_trace", "turn_perf_trace"]


def test_phase13_35_console_backfill_writes_turn_error_events(tmp_path: Path):
    console = tmp_path / "console-log.txt"
    console.write_text(
        "[2026-01-01T00:00:00] TURN 61 " + hook._EVENT_WORD + ": RuntimeError: backfill boom\n"
        "[AUTOPLAY-PROBE] ts=2026-01-01T00:00:01 event=runtime_turn_execution.result "
        "thread=MainThread turn_index=61 ok=False keys=manual_harness_trace\n",
        encoding="utf-8",
    )

    payload = hook.backfill_runtime_turn_results_from_console_log(tmp_path)
    assert payload["event_count"] == 1

    error_payload = json.loads((tmp_path / hook.TURN_ERROR_ARTIFACT_NAME).read_text(encoding="utf-8"))
    assert error_payload["event_count"] == 1
    event = error_payload["events"][0]
    assert event["capture_source"] == "console_log"
    assert event["turn_index"] == 61
    assert event["error_type"] == "RuntimeError"
    assert event["message"] == "backfill boom"
