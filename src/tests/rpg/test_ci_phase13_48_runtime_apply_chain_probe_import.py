import json
import zipfile
from pathlib import Path

from tests.rpg.autoplay import runtime_apply_chain_probe as probe


def _reset_probe(tmp_path: Path):
    probe.uninstall_runtime_apply_chain_probe()
    probe._OUTPUT_DIR = tmp_path
    probe._INSTALLED = False
    probe._PREVIOUS_TRACE = None


def test_phase13_48_runtime_apply_chain_probe_import_and_artifact(tmp_path: Path):
    _reset_probe(tmp_path)

    probe.install_runtime_apply_chain_probe_from_argv(["--output-dir", str(tmp_path)])
    payload = probe.write_runtime_apply_chain_probe_artifact()
    probe.uninstall_runtime_apply_chain_probe()

    assert payload["source"] == "autoplay_runtime_apply_chain_probe_v2"
    assert payload["installed"] is True
    path = tmp_path / "autoplay-runtime-apply-chain-probe.json"
    assert path.exists()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["source"] == "autoplay_runtime_apply_chain_probe_v2"
    assert loaded["event_count"] >= 1
    assert loaded["events"][0]["event_class"] == "runtime_apply_chain_trace_installed"


def test_phase13_48_runtime_apply_chain_probe_output_dir_from_equals_arg(tmp_path: Path):
    output_dir = probe._output_dir_from_argv([f"--output-dir={tmp_path}"])
    assert output_dir == tmp_path


def test_phase13_49_runtime_apply_chain_probe_safe_json_marks_cycles():
    payload = {"name": "root"}
    payload["self"] = payload

    safe = probe._safe_json(payload)

    assert safe["name"] == "root"
    assert safe["self"]["__cycle__"] is True


def test_phase13_49_runtime_apply_chain_probe_records_manual_turn_return(tmp_path: Path):
    _reset_probe(tmp_path)
    probe.install_runtime_apply_chain_probe_from_argv(["--output-dir", str(tmp_path)])

    def _run_one_manual_turn(turn_index: int):
        recursive = {"turn_index": turn_index, "error": "RecursionError: maximum recursion depth exceeded"}
        recursive["self"] = recursive
        return recursive

    result = _run_one_manual_turn(7)
    probe.uninstall_runtime_apply_chain_probe()

    assert result["turn_index"] == 7
    artifact = json.loads((tmp_path / "autoplay-runtime-apply-chain-probe.json").read_text(encoding="utf-8"))
    event_classes = [event["event_class"] for event in artifact["events"]]
    assert "runtime_apply_chain_enter" in event_classes
    assert "runtime_apply_chain_return" in event_classes
    return_events = [event for event in artifact["events"] if event["event_class"] == "runtime_apply_chain_return"]
    assert return_events[-1]["return_payload_shape"]["has_error"] is True
    assert return_events[-1]["return_payload_shape"]["safe_excerpt"]["self"]["__cycle__"] is True


def test_phase13_49_runtime_apply_chain_probe_appends_to_result_zip(tmp_path: Path):
    _reset_probe(tmp_path)
    zip_path = tmp_path / "interactive-campaign-results.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("interactive-summary.json", "{}")

    probe.install_runtime_apply_chain_probe_from_argv(["--output-dir", str(tmp_path)])
    append_result = probe.append_runtime_apply_chain_probe_to_result_zips()
    probe.uninstall_runtime_apply_chain_probe()

    assert append_result["zips_appended"] == [str(zip_path)]
    with zipfile.ZipFile(zip_path, "r") as zf:
        assert "autoplay-runtime-apply-chain-probe.json" in zf.namelist()
        payload = json.loads(zf.read("autoplay-runtime-apply-chain-probe.json").decode("utf-8"))
    assert payload["source"] == "autoplay_runtime_apply_chain_probe_v2"
