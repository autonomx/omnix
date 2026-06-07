import copy
import json
from pathlib import Path

import tests.rpg.autoplay_llm_campaign as loader
from tests.rpg.autoplay import deepcopy_recursion_guard as guard
from tests.rpg.autoplay.deepcopy_recursion_guard import (
    SUMMARY_NAME,
    _parse_output_dir,
    guarded_deepcopy,
    install_deepcopy_recursion_guard,
)


class CopyRaises:
    def __deepcopy__(self, memo):
        raise RecursionError("forced copy failure")


def test_phase13_13_loader_parses_explicit_output_dir(tmp_path: Path):
    assert loader._output_dir_from_argv(["--output-dir", str(tmp_path)]) == tmp_path
    assert loader._output_dir_from_argv([f"--output-dir={tmp_path}"]) == tmp_path
    assert loader._output_dir_from_argv(["--turns", "100"]) is None
    assert _parse_output_dir(["--output-dir", str(tmp_path)]) == tmp_path


def test_phase13_13_guarded_copy_writes_summary(tmp_path: Path):
    guard._OUTPUT_DIR = tmp_path
    result = guarded_deepcopy({"bad": CopyRaises(), "ok": [1, 2, 3]})

    assert "bad" in result
    assert result["ok"] == [1, 2, 3]
    summary = json.loads((tmp_path / SUMMARY_NAME).read_text(encoding="utf-8"))
    assert summary["fallback_count"] == 1
    assert summary["events"][0]["error_type"] == "RecursionError"


def test_phase13_13_safe_clone_breaks_self_reference():
    payload = {}
    payload["self"] = payload
    cloned = guard._safe_clone(payload)
    assert cloned["self"]["__cycle__"] is True


def test_phase13_13_install_patches_copy(tmp_path: Path):
    original = copy.deepcopy
    try:
        guard._INSTALLED = False
        install_deepcopy_recursion_guard(output_dir=tmp_path)
        assert copy.deepcopy is guarded_deepcopy
    finally:
        copy.deepcopy = original
        guard._INSTALLED = False
