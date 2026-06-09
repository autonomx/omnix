import json
from pathlib import Path

from tests.rpg.autoplay import runtime_probe_payload_capture as hook


def test_phase13_37_artifact_path_uses_default_output_dir(tmp_path: Path, monkeypatch):
    original_output_dir = hook._OUTPUT_DIR
    monkeypatch.chdir(tmp_path)
    try:
        hook._OUTPUT_DIR = None
        path = hook.artifact_path()
    finally:
        hook._OUTPUT_DIR = original_output_dir

    assert path == tmp_path.joinpath(*hook._DEFAULT_AUTOPLAY_RESULT_DIR_PARTS) / hook.ARTIFACT_NAME


def test_phase13_37_probe_log_is_wrappable():
    def _probe_log(enabled, event_name, **kwargs):
        return {"enabled": enabled, "event": event_name, "kwargs": kwargs}

    assert hook.should_wrap_probe_function("_probe_log", _probe_log) is True
    assert hook.should_wrap_probe_function("probe_log", _probe_log) is True


def test_phase13_37_wrapper_captures_caller_locals(tmp_path: Path):
    original_output_dir = hook._OUTPUT_DIR
    original_wrapped = set(hook._WRAPPED_NAMES)
    namespace = {}

    def _probe_log(enabled, event_name, **kwargs):
        return {"enabled": enabled, "event": event_name, "kwargs": kwargs}

    namespace["_probe_log"] = _probe_log
    try:
        hook._OUTPUT_DIR = tmp_path
        hook._WRAPPED_NAMES.clear()
        result = hook.wrap_runtime_probe_functions(namespace)
        assert result["wrapped_names"] == ["_probe_log"]

        def emit_probe():
            turn_index = 59
            runtime_error = "RuntimeError: boom"
            turn_result = {"ok": False, "error": runtime_error, "runtime_name": "probe-runtime"}
            return namespace["_probe_log"](
                True,
                "runtime_turn_execution.result",
                turn_index=turn_index,
                ok=turn_result.get("ok"),
                keys=",".join(sorted(turn_result.keys())),
            )

        emit_probe()
    finally:
        hook._OUTPUT_DIR = original_output_dir
        hook._WRAPPED_NAMES.clear()
        hook._WRAPPED_NAMES.update(original_wrapped)

    payload = json.loads((tmp_path / hook.ARTIFACT_NAME).read_text(encoding="utf-8"))
    assert payload["source"] == hook.SOURCE
    assert payload["event_count"] == 2
    caller_event = payload["events"][0]
    call_event = payload["events"][1]
    assert caller_event["event_class"] == "runtime_probe_caller_locals"
    assert caller_event["turn_index"] == 59
    assert caller_event["locals"]["runtime_error"] == "RuntimeError: boom"
    assert caller_event["locals"]["turn_result"]["ok"] is False
    assert caller_event["locals"]["turn_result"]["error"] == "RuntimeError: boom"
    assert call_event["event_class"] == "runtime_probe_call"
    assert call_event["payload"]["turn_index"] == 59
