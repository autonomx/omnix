import json
from pathlib import Path

from tests.rpg.autoplay.result_path_diagnostics import SUMMARY_NAME, write_result_path_diagnostics


def test_phase13_29_result_path_diagnostics_preserves_turn_error_hook_events(tmp_path: Path):
    summary_path = tmp_path / SUMMARY_NAME
    hook_payload = {
        "ok": True,
        "source": "autoplay_turn_error_diagnostics_hook_v2",
        "event_count": 1,
        "events": [
            {
                "turn_index": 59,
                "error_type": "RuntimeError",
                "active_exception_available": True,
                "active_exception": {
                    "ok": True,
                    "traceback_frames": [
                        {
                            "filename": "runtime.py",
                            "line_number": 10,
                            "function_name": "problem_path",
                            "line": "raise RuntimeError('boom')",
                        }
                    ],
                    "repeated_frames": [],
                    "formatted_traceback_tail": ["RuntimeError: boom"],
                },
                "source": "autoplay_turn_error_diagnostics_hook_v2",
            }
        ],
    }
    summary_path.write_text(json.dumps(hook_payload), encoding="utf-8")
    (tmp_path / "autoplay-summary.json").write_text(json.dumps({"ok": True}), encoding="utf-8")

    result = write_result_path_diagnostics(tmp_path)
    payload = json.loads(summary_path.read_text(encoding="utf-8"))

    assert result["source"] == "autoplay_result_path_diagnostics_v5"
    assert payload["turn_error_hook_source"] == "autoplay_turn_error_diagnostics_hook_v2"
    assert payload["turn_error_hook_event_count"] == 1
    assert payload["turn_error_hook_active_exception_event_count"] == 1
    preserved = payload["turn_error_hook_events"][0]
    assert preserved["turn_index"] == 59
    assert preserved["active_exception_available"] is True
    assert preserved["active_exception"]["traceback_frames"][0]["function_name"] == "problem_path"
