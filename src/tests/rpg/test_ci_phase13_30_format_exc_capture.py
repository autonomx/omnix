import builtins
import json
import traceback
from pathlib import Path

from tests.rpg.autoplay import turn_error_diagnostics_hook as hook
from tests.rpg.autoplay.turn_error_diagnostics_hook import (
    FORMAT_EXC_NAME,
    SUMMARY_NAME,
    install_turn_error_diagnostics_hook,
)


def _raise_for_capture(turn_index: int) -> None:
    def inner() -> None:
        raise ValueError("boom")

    inner()


def test_phase13_30_format_exc_capture_records_active_context(tmp_path: Path):
    original_format_exc = traceback.format_exc
    try:
        install_turn_error_diagnostics_hook(output_dir=tmp_path)
        try:
            _raise_for_capture(77)
        except ValueError:
            text = traceback.format_exc()
            assert "ValueError" in text
    finally:
        traceback.format_exc = original_format_exc  # type: ignore[assignment]

    payload = json.loads((tmp_path / FORMAT_EXC_NAME).read_text(encoding="utf-8"))
    assert payload["source"] == hook.SOURCE
    assert payload["event_count"] == 1
    event = payload["events"][0]
    assert event["event_class"] == "traceback_format_exc"
    assert event["active_exception_available"] is True
    assert event["turn_index"] == 77
    active = event["active_exception"]
    assert active["ok"] is True
    assert active["error_type"] == "ValueError"
    functions = [frame["function_name"] for frame in active["traceback_frames"]]
    assert "_raise_for_capture" in functions
    assert "inner" in functions
    assert event["formatted_text_tail"]


def test_phase13_34_line_capture_uses_default_output_dir(tmp_path: Path, monkeypatch):
    original_print = builtins.print
    original_output_dir = hook._OUTPUT_DIR
    monkeypatch.chdir(tmp_path)
    try:
        hook._OUTPUT_DIR = None
        hook._record_line("[probe] TURN 59 " + hook._EVENT_WORD + ": ValueError: boom")
    finally:
        hook._OUTPUT_DIR = original_output_dir
        builtins.print = original_print

    path = tmp_path.joinpath(*hook._DEFAULT_AUTOPLAY_RESULT_DIR_PARTS) / SUMMARY_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["source"] == hook.SOURCE
    assert payload["event_count"] == 1
    event = payload["events"][0]
    assert event["turn_index"] == 59
    assert event["error_type"] == "ValueError"
    assert event["message"] == "boom"


def test_phase13_34_format_capture_uses_default_output_dir(tmp_path: Path, monkeypatch):
    original_output_dir = hook._OUTPUT_DIR
    monkeypatch.chdir(tmp_path)
    try:
        hook._OUTPUT_DIR = None
        try:
            _raise_for_capture(88)
        except ValueError:
            hook._record_format_exc_event("formatted default")
    finally:
        hook._OUTPUT_DIR = original_output_dir

    path = tmp_path.joinpath(*hook._DEFAULT_AUTOPLAY_RESULT_DIR_PARTS) / FORMAT_EXC_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["source"] == hook.SOURCE
    assert payload["event_count"] == 1
    event = payload["events"][0]
    assert event["event_class"] == "traceback_format_exc"
    assert event["active_exception_available"] is True
    assert event["turn_index"] == 88
