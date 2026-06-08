import json
import traceback
from pathlib import Path

from tests.rpg.autoplay.deepcopy_recursion_guard import install_deepcopy_recursion_guard
from tests.rpg.autoplay.runtime_recursion_perf_probe import SUMMARY_NAME, run_targeted_recursion_perf_probe
from tests.rpg.autoplay.turn_error_diagnostics_hook import FORMAT_EXC_NAME, install_turn_error_diagnostics_hook


def test_phase13_31_targeted_probe_runs_with_runtime_diagnostics_hooks(tmp_path: Path):
    original_format_exc = traceback.format_exc
    try:
        install_turn_error_diagnostics_hook(output_dir=tmp_path)
        install_deepcopy_recursion_guard(output_dir=tmp_path)
        summary = run_targeted_recursion_perf_probe(output_dir=tmp_path, depth=10, fanout=2)
    finally:
        traceback.format_exc = original_format_exc  # type: ignore[assignment]

    assert summary["ok"] is True
    assert (tmp_path / SUMMARY_NAME).exists()
    payload = json.loads((tmp_path / SUMMARY_NAME).read_text(encoding="utf-8"))
    assert payload["operations"]
    assert any(entry["name"] == "traceback.format_exc" for entry in payload["operations"])
    assert (tmp_path / FORMAT_EXC_NAME).exists()
    trace_payload = json.loads((tmp_path / FORMAT_EXC_NAME).read_text(encoding="utf-8"))
    assert trace_payload["event_count"] >= 1
