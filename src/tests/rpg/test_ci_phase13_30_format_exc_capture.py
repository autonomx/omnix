import json
import traceback
from pathlib import Path

from tests.rpg.autoplay.turn_error_diagnostics_hook import (
    FORMAT_EXC_NAME,
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
    assert payload["source"] == "autoplay_turn_error_diagnostics_hook_v3"
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
