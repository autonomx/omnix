from tests.rpg.autoplay.probe_source_map import build_probe_source_map_from_source


def test_phase13_36_runtime_source_map_includes_function_context():
    source = """
def outer():
    value = 1
    def inner(turn_index):
        turn_result = {
            \"traceback\": _capture_runtime_exception_traceback(traceback.format_exc(), turn_index=turn_index),
        }
        _probe_log(
            True,
            \"runtime_turn_execution.result\",
            turn_index=turn_index,
            ok=turn_result.get(\"ok\"),
        )
        return turn_result
"""

    payload = build_probe_source_map_from_source(source, filename="combined.py")
    matches = payload["matches"]
    probe_matches = [match for match in matches if "runtime_turn_execution.result" in match["event_texts"]]
    capture_matches = [match for match in matches if "_capture_runtime_exception_traceback" in match["event_texts"]]

    assert payload["source"] == "autoplay_probe_source_map_v2"
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
    line = f\"TURN {turn_index} \" + (\"ERR\" + \"OR:\") + f\" {error_type}: {message}\"
    print(line)
"""
    payload = build_probe_source_map_from_source(source, filename="combined.py")
    matches = payload["matches"]
    assert any("TURN" in match["event_texts"] for match in matches)
    assert any("ERROR:" in match["event_texts"] for match in matches)
    assert all(match["function_context"] for match in matches)
