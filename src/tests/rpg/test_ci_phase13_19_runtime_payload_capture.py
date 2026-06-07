import json
from pathlib import Path

from tests.rpg.autoplay.result_path_diagnostics import (
    RUNTIME_TURN_PAYLOADS_NAME,
    collect_result_path_diagnostics,
)
from tests.rpg.autoplay.runtime_probe_payload_capture import (
    artifact_path,
    capture_runtime_probe_locals,
    configure_runtime_probe_payload_capture,
    instrument_runtime_probe_source,
    should_wrap_probe_function,
    wrap_runtime_probe_functions,
)
from tests.rpg.autoplay.survival_report_writer_hook import (
    load_runtime_probe_payload_rows,
    run_autoplay_survival_report_writer_hook,
)


def test_phase13_19_preserves_generated_runtime_source():
    source = "def f():\n    print('event=runtime_turn_execution.result', result)\n"

    instrumented = instrument_runtime_probe_source(source)

    assert instrumented == source
    assert "event=runtime_turn_execution.result" in instrumented


def test_phase13_19_capture_runtime_probe_locals_writes_payload(tmp_path: Path):
    configure_runtime_probe_payload_capture(output_dir=tmp_path)
    turn_result = {
        "ok": False,
        "runtime_name": "runtime_turn_execution",
        "manual_stage_trace": [{"stage": "runtime", "duration_ms": 1}],
        "turn_perf_trace_summary": {"manual_turn_ms": {"avg_ms": 10, "count": 1}},
    }

    capture_runtime_probe_locals({"turn_index": 59, "turn_result": turn_result, "player_input": "continue"})

    path = artifact_path()
    assert path == tmp_path / RUNTIME_TURN_PAYLOADS_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["event_count"] == 1
    event = payload["events"][0]
    assert event["turn_index"] == 59
    assert event["locals"]["turn_result"]["runtime_name"] == "runtime_turn_execution"


def test_phase13_19_wrap_runtime_probe_function_records_call(tmp_path: Path):
    configure_runtime_probe_payload_capture(output_dir=tmp_path)
    calls = []

    def emit_probe(event, **kwargs):
        calls.append((event, kwargs))
        return "ok"

    namespace = {"emit_probe": emit_probe}
    result = wrap_runtime_probe_functions(namespace)

    assert result["wrapped_count"] == 1
    assert namespace["emit_probe"]("event=runtime_turn_execution.result", turn_index=60, result={"ok": False}) == "ok"
    assert calls
    payload = json.loads((tmp_path / RUNTIME_TURN_PAYLOADS_NAME).read_text(encoding="utf-8"))
    assert payload["event_count"] == 1
    assert payload["events"][0]["event_class"] == "runtime_probe_call"


def test_phase13_19_does_not_wrap_real_autoplay_runner_or_facade_symbols():
    def _run_real_autoplay():
        return "real"

    def _assert_real_autoplay_runner_present():
        return True

    def _runtime_facade_manifest_gate():
        return True

    def _call_turn_runtime():
        return {"ok": True}

    namespace = {
        "_run_real_autoplay": _run_real_autoplay,
        "_assert_real_autoplay_runner_present": _assert_real_autoplay_runner_present,
        "_runtime_facade_manifest_gate": _runtime_facade_manifest_gate,
        "_call_turn_runtime": _call_turn_runtime,
    }

    result = wrap_runtime_probe_functions(namespace)

    assert result["wrapped_count"] == 0
    assert namespace["_run_real_autoplay"] is _run_real_autoplay
    assert namespace["_assert_real_autoplay_runner_present"] is _assert_real_autoplay_runner_present
    assert namespace["_runtime_facade_manifest_gate"] is _runtime_facade_manifest_gate
    assert namespace["_call_turn_runtime"] is _call_turn_runtime
    assert not should_wrap_probe_function("_run_real_autoplay", _run_real_autoplay)
    assert not should_wrap_probe_function("_assert_real_autoplay_runner_present", _assert_real_autoplay_runner_present)
    assert not should_wrap_probe_function("_runtime_facade_manifest_gate", _runtime_facade_manifest_gate)
    assert not should_wrap_probe_function("_call_turn_runtime", _call_turn_runtime)


def test_phase13_19_result_diagnostics_prioritizes_payload_capture(tmp_path: Path):
    payload = {
        "events": [
            {
                "event_class": "runtime_probe_locals",
                "runtime_result": True,
                "turn_index": 61,
                "locals": {
                    "turn_result": {
                        "ok": False,
                        "runtime_name": "runtime_turn_execution",
                        "manual_stage_trace": [{"stage": "runtime", "duration_ms": 1}],
                        "turn_perf_trace_summary": {"manual_turn_ms": {"avg_ms": 10, "count": 1}},
                    }
                },
            }
        ]
    }
    (tmp_path / RUNTIME_TURN_PAYLOADS_NAME).write_text(json.dumps(payload), encoding="utf-8")

    diagnostics = collect_result_path_diagnostics(tmp_path)

    assert diagnostics["runtime_result_event_count"] >= 1
    event = diagnostics["runtime_result_events"][0]
    assert event["event_class"] == "runtime_probe_locals"
    assert event["turn_index"] == 61
    assert "manual_stage_trace" in event["trace_keys_present"]
    assert "captured_locals" in event["traces"]


def test_phase13_19_post_run_hook_counts_payload_rows(tmp_path: Path):
    (tmp_path / RUNTIME_TURN_PAYLOADS_NAME).write_text(
        json.dumps(
            {
                "events": [
                    {
                        "event_class": "runtime_probe_locals",
                        "runtime_result": True,
                        "turn_index": 62,
                        "locals": {
                            "turn_result": {
                                "ok": False,
                                "runtime_name": "runtime_turn_execution",
                                "turn_perf_trace_summary": {"manual_turn_ms": {"avg_ms": 10, "count": 1}},
                            }
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    rows = load_runtime_probe_payload_rows(tmp_path)
    result = run_autoplay_survival_report_writer_hook(
        script_path=Path("src/tests/rpg/autoplay_llm_campaign.py"),
        results_dir=tmp_path,
    )

    assert len(rows) == 1
    assert result["ok"] is True
    assert result["runtime_probe_payload_rows_observed"] == 1
    assert result["result_path_diagnostics"]["runtime_result_event_count"] >= 1
