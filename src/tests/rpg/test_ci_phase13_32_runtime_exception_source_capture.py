import json
import types
from pathlib import Path

import tests.rpg.autoplay_llm_campaign as loader


def test_phase13_32_instruments_runtime_traceback_expression():
    source = 'turn_result = {"traceback": traceback.format_exc(), "ok": False}'
    instrumented = loader._instrument_runtime_exception_traceback_capture(source)
    assert loader._RUNTIME_TRACEBACK_CAPTURE_EXPR in instrumented
    assert loader._RUNTIME_TRACEBACK_SOURCE_EXPR not in instrumented


def test_phase13_32_capture_runtime_exception_traceback_writes_artifact(tmp_path: Path):
    original_output_dir = loader._RUNTIME_EXCEPTION_TRACEBACK_OUTPUT_DIR
    try:
        loader._RUNTIME_EXCEPTION_TRACEBACK_OUTPUT_DIR = tmp_path
        try:
            raise ValueError("boom")
        except ValueError:
            text = loader._capture_runtime_exception_traceback("formatted boom", turn_index=59)
    finally:
        loader._RUNTIME_EXCEPTION_TRACEBACK_OUTPUT_DIR = original_output_dir

    assert text == "formatted boom"
    path = tmp_path / "autoplay-exception-tracebacks.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["source"] == "autoplay_runtime_exception_source_capture_v1"
    assert payload["event_count"] == 1
    event = payload["events"][0]
    assert event["event_class"] == "runtime_exception_source_capture"
    assert event["turn_index"] == 59
    assert event["active_exception_available"] is True
    assert event["error_type"] == "ValueError"
    assert event["traceback_frames"]
    assert event["formatted_text_tail"] == "formatted boom"


def test_phase13_32_instrumented_expression_preserves_traceback_value(tmp_path: Path):
    original_output_dir = loader._RUNTIME_EXCEPTION_TRACEBACK_OUTPUT_DIR
    namespace = {
        "traceback": __import__("traceback"),
        "_capture_runtime_exception_traceback": loader._capture_runtime_exception_traceback,
        "turn_index": 77,
    }
    source = "result = {\"traceback\": traceback.format_exc(), \"ok\": False}"
    instrumented = loader._instrument_runtime_exception_traceback_capture(source)
    try:
        loader._RUNTIME_EXCEPTION_TRACEBACK_OUTPUT_DIR = tmp_path
        try:
            raise RuntimeError("runtime boom")
        except RuntimeError:
            exec(instrumented, namespace, namespace)
    finally:
        loader._RUNTIME_EXCEPTION_TRACEBACK_OUTPUT_DIR = original_output_dir

    result = namespace["result"]
    assert "RuntimeError" in result["traceback"]
    payload = json.loads((tmp_path / "autoplay-exception-tracebacks.json").read_text(encoding="utf-8"))
    assert payload["events"][0]["turn_index"] == 77
