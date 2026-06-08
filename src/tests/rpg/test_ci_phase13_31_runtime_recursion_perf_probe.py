import json
from pathlib import Path

from tests.rpg.autoplay.runtime_recursion_perf_probe import (
    SUMMARY_NAME,
    bounded_json_clone,
    make_self_referential_turn_payload,
    run_targeted_recursion_perf_probe,
)


def test_phase13_31_bounded_clone_marks_cycles_without_error():
    payload = make_self_referential_turn_payload(depth=8, fanout=2)
    cloned = bounded_json_clone(payload, max_depth=10, max_items=20)
    text = json.dumps(cloned, sort_keys=True)
    assert "__cycle__" in text
    assert "targeted_probe_runtime" in text


def test_phase13_31_targeted_probe_writes_operation_breakdown(tmp_path: Path):
    summary = run_targeted_recursion_perf_probe(output_dir=tmp_path, depth=8, fanout=2)
    path = tmp_path / SUMMARY_NAME
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    names = {entry["name"] for entry in payload["operations"]}
    assert summary["ok"] is True
    assert "copy.deepcopy" in names
    assert "bounded_json_clone" in names
    assert "json.dumps_bounded_clone" in names
    assert "traceback.format_exc" in names
    assert payload["source"] == "autoplay_runtime_recursion_perf_probe_v1"
    for entry in payload["operations"]:
        assert isinstance(entry["elapsed_ms"], float)


def test_phase13_31_probe_flags_failed_or_slow_recursive_operations(tmp_path: Path):
    payload = run_targeted_recursion_perf_probe(output_dir=tmp_path, depth=20, fanout=3)
    operations = {entry["name"]: entry for entry in payload["operations"]}
    assert operations["bounded_json_clone"]["ok"] is True
    assert operations["json.dumps_bounded_clone"]["ok"] is True
    assert "failed_operations" in payload
    assert "slow_operations" in payload
