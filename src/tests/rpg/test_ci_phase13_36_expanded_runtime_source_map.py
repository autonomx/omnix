import atexit
from pathlib import Path

import tests.rpg.autoplay.probe_source_map as source_map
from tests.rpg.autoplay.probe_source_map import build_probe_source_map_from_source


def test_phase13_36_runtime_source_map_includes_function_context():
    source = """
def outer():
    value = 1
    def inner(turn_index):
        turn_result = {
            "traceback": _capture_runtime_exception_traceback(traceback.format_exc(), turn_index=turn_index),
        }
        _probe_log(
            True,
            "runtime_turn_execution.result",
            turn_index=turn_index,
            ok=turn_result.get("ok"),
        )
        return turn_result
"""

    payload = build_probe_source_map_from_source(source, filename="combined.py")
    matches = payload["matches"]
    probe_matches = [match for match in matches if "runtime_turn_execution.result" in match["event_texts"]]
    capture_matches = [match for match in matches if "_capture_runtime_exception_traceback" in match["event_texts"]]

    assert payload["source"] == "autoplay_probe_source_map_v4"
    assert probe_matches
    assert capture_matches
    probe = probe_matches[0]
    assert probe["enclosing_function_name"] == "inner"
    assert probe["function_context"]
    function_text = "\n".join(line["text"] for line in probe["function_context"])
    assert "turn_result" in function_text
    assert "runtime_turn_execution.result" in function_text
    assert "_capture_runtime_exception_traceback" in function_text


def test_phase13_36_runtime_source_map_matches_turn_failure_emission():
    source = """
def emit(turn_index, error_type, message):
    line = f"TURN {turn_index} " + ("ERR" + "OR:") + f" {error_type}: {message}"
    print(line)
"""
    payload = build_probe_source_map_from_source(source, filename="combined.py")
    matches = payload["matches"]
    assert any("TURN" in match["event_texts"] for match in matches)
    assert any("ERROR:" in match["event_texts"] for match in matches)
    assert all(match["function_context"] for match in matches)


def test_phase13_43_runtime_source_map_matches_runtime_core_markers():
    source = """
def run_runtime_core(turn_perf_trace):
    turn_perf_trace.append({"event": "runtime_checkpoint_before_companion_systems"})
    state = apply_companion_systems()
    turn_perf_trace.append({"event": "runtime_core_before_apply_turn_authoritative"})
    result = apply_turn_authoritative(state)
    turn_perf_trace.append({"event": "runtime_core_after_apply_turn_authoritative"})
    return result
"""
    payload = build_probe_source_map_from_source(source, filename="combined.py")
    matches = payload["matches"]
    event_texts = [text for match in matches for text in match["event_texts"]]

    assert "runtime_checkpoint_before_companion_systems" in event_texts
    assert "runtime_core_before_apply_turn_authoritative" in event_texts
    assert "runtime_core_after_apply_turn_authoritative" in event_texts
    core_match = next(match for match in matches if "runtime_core_before_apply_turn_authoritative" in match["event_texts"])
    assert core_match["enclosing_function_name"] == "run_runtime_core"
    context_text = "\n".join(line["text"] for line in core_match["context"])
    assert "apply_turn_authoritative" in context_text


def test_phase13_44_configure_registers_source_map_atexit_once(tmp_path: Path, monkeypatch):
    registered = []
    original_output_dir = source_map._OUTPUT_DIR
    original_registered = source_map._ATEXIT_REGISTERED
    try:
        source_map._OUTPUT_DIR = None
        source_map._ATEXIT_REGISTERED = False
        monkeypatch.setattr(atexit, "register", lambda fn: registered.append(fn))
        source_map.configure_probe_source_map(output_dir=tmp_path)
        source_map.configure_probe_source_map(output_dir=tmp_path)
    finally:
        source_map._OUTPUT_DIR = original_output_dir
        source_map._ATEXIT_REGISTERED = original_registered

    assert source_map.SOURCE == "autoplay_probe_source_map_v4"
    assert source_map._OUTPUT_DIR == original_output_dir
    assert len(registered) == 1
    assert registered[0].__name__ == "_write_probe_source_map_at_exit"
