import json
from pathlib import Path

from tests.rpg.autoplay import runtime_apply_chain_probe as probe


def test_phase13_48_runtime_apply_chain_probe_import_and_artifact(tmp_path: Path):
    probe._OUTPUT_DIR = tmp_path
    probe._INSTALLED = False

    probe.install_runtime_apply_chain_probe_from_argv(["--output-dir", str(tmp_path)])
    payload = probe.write_runtime_apply_chain_probe_artifact()

    assert payload["source"] == "autoplay_runtime_apply_chain_probe_v1"
    assert payload["installed"] is True
    assert payload["event_count"] == 0
    path = tmp_path / "autoplay-runtime-apply-chain-probe.json"
    assert path.exists()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["source"] == "autoplay_runtime_apply_chain_probe_v1"


def test_phase13_48_runtime_apply_chain_probe_output_dir_from_equals_arg(tmp_path: Path):
    output_dir = probe._output_dir_from_argv([f"--output-dir={tmp_path}"])
    assert output_dir == tmp_path
