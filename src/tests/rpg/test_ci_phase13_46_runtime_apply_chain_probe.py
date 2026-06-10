from pathlib import Path
from types import SimpleNamespace

from tests.rpg.autoplay import live_manual_turn_timing as timing


def test_phase13_46_records_runtime_apply_chain_event(tmp_path: Path):
    original_output_dir = timing._OUTPUT_DIR
    try:
        timing._OUTPUT_DIR = tmp_path
        timing.record_runtime_apply_chain_event(
            module_name="unit.runtime_part01",
            function_name="_apply_turn_authoritative",
            elapsed_ms=12.3456,
            ok=False,
            error=RecursionError("maximum recursion depth exceeded"),
        )
    finally:
        timing._OUTPUT_DIR = original_output_dir

    path = tmp_path / timing.RUNTIME_CHAIN_ARTIFACT_NAME
    assert path.exists()
    payload = __import__("json").loads(path.read_text(encoding="utf-8"))
    assert payload["source"] == timing.RUNTIME_CHAIN_SOURCE
    assert payload["event_count"] == 1
    event = payload["events"][0]
    assert event["module_name"] == "unit.runtime_part01"
    assert event["function_name"] == "_apply_turn_authoritative"
    assert event["ok"] is False
    assert event["error_type"] == "RecursionError"
    assert "maximum recursion" in event["error_tail"]
    assert payload["module_summary"]["unit.runtime_part01"]["error_count"] == 1


def test_phase13_46_wrap_runtime_apply_callable_preserves_result(tmp_path: Path):
    original_output_dir = timing._OUTPUT_DIR
    module = SimpleNamespace(__name__="unit.runtime")

    def _apply_turn_authoritative(*args, **kwargs):
        return {"ok": True, "args": args, "kwargs": kwargs}

    module._apply_turn_authoritative = _apply_turn_authoritative
    try:
        timing._OUTPUT_DIR = tmp_path
        assert timing._wrap_runtime_apply_callable(module, "_apply_turn_authoritative") is True
        result = module._apply_turn_authoritative("session", "look", action={"kind": "look"})
    finally:
        timing._OUTPUT_DIR = original_output_dir
        timing._RUNTIME_CHAIN_WRAPPED.discard("unit.runtime:_apply_turn_authoritative")

    assert result["ok"] is True
    payload = __import__("json").loads((tmp_path / timing.RUNTIME_CHAIN_ARTIFACT_NAME).read_text(encoding="utf-8"))
    assert payload["events"][0]["ok"] is True
    assert payload["events"][0]["module_name"] == "unit.runtime"


def test_phase13_46_wrap_runtime_apply_callable_records_exceptions(tmp_path: Path):
    original_output_dir = timing._OUTPUT_DIR
    module = SimpleNamespace(__name__="unit.runtime.error")

    def _apply_turn_authoritative(*args, **kwargs):
        raise RecursionError("boom")

    module._apply_turn_authoritative = _apply_turn_authoritative
    try:
        timing._OUTPUT_DIR = tmp_path
        assert timing._wrap_runtime_apply_callable(module, "_apply_turn_authoritative") is True
        try:
            module._apply_turn_authoritative("session", "look")
        except RecursionError:
            pass
    finally:
        timing._OUTPUT_DIR = original_output_dir
        timing._RUNTIME_CHAIN_WRAPPED.discard("unit.runtime.error:_apply_turn_authoritative")

    payload = __import__("json").loads((tmp_path / timing.RUNTIME_CHAIN_ARTIFACT_NAME).read_text(encoding="utf-8"))
    event = payload["events"][0]
    assert event["ok"] is False
    assert event["error_type"] == "RecursionError"
    assert event["error_tail"] == "boom"
