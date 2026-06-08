import builtins
import json
from pathlib import Path

from tests.rpg.autoplay.turn_error_diagnostics_hook import install_turn_error_diagnostics_hook


def _raise_nested_error() -> None:
    def inner() -> None:
        raise RuntimeError("boom")

    inner()


def test_phase13_28_turn_error_hook_captures_active_exception_traceback(tmp_path: Path):
    original_print = builtins.print
    try:
        install_turn_error_diagnostics_hook(output_dir=tmp_path)
        try:
            _raise_nested_error()
        except RuntimeError:
            print("TURN 59 ERROR: RuntimeError: boom")
    finally:
        builtins.print = original_print

    payload = json.loads((tmp_path / "autoplay-turn-error-diagnostics.json").read_text(encoding="utf-8"))
    assert payload["source"] == "autoplay_turn_error_diagnostics_hook_v2"
    assert payload["event_count"] == 1
    event = payload["events"][0]
    assert event["turn_index"] == 59
    assert event["error_type"] == "RuntimeError"
    assert event["active_exception_available"] is True
    active = event["active_exception"]
    assert active["ok"] is True
    assert active["error_type"] == "RuntimeError"
    assert active["traceback_frame_count"] >= 2
    functions = [frame["function_name"] for frame in active["traceback_frames"]]
    assert "_raise_nested_error" in functions
    assert "inner" in functions
    assert active["formatted_traceback_tail"]


def test_phase13_28_turn_error_hook_records_no_active_exception_when_printed_outside_except(tmp_path: Path):
    original_print = builtins.print
    try:
        install_turn_error_diagnostics_hook(output_dir=tmp_path)
        print("TURN 60 ERROR: RuntimeError: boom")
    finally:
        builtins.print = original_print

    payload = json.loads((tmp_path / "autoplay-turn-error-diagnostics.json").read_text(encoding="utf-8"))
    event = payload["events"][0]
    assert event["active_exception_available"] is False
    assert event["active_exception"]["reason"] == "no_active_exception"
