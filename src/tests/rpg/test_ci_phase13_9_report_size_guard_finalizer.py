import json
import zipfile
from pathlib import Path

from app.rpg.autoplay_report_size_guard import REPORT_JSON_NAME, SIZE_GUARD_SOURCE
from tests.rpg.autoplay.report_size_guard_hook import (
    _output_dir_from_argv,
    run_report_size_guard_from_argv,
)


def test_phase13_9_output_dir_is_parsed_from_argv_forms(tmp_path: Path):
    assert _output_dir_from_argv(["--output-dir", str(tmp_path)]) == tmp_path
    assert _output_dir_from_argv([f"--output-dir={tmp_path}"]) == tmp_path
    assert _output_dir_from_argv(["--turns", "100"]) is None


def test_phase13_9_guard_caps_explicit_output_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RPG_AUTOPLAY_MAX_REPORT_JSON_BYTES", "64")
    report = tmp_path / REPORT_JSON_NAME
    report.write_text(json.dumps({"rows": ["x" * 200]}), encoding="utf-8")
    with zipfile.ZipFile(tmp_path / "autoplay-campaign-results.zip", "w") as zf:
        zf.writestr(REPORT_JSON_NAME, json.dumps({"rows": ["x" * 200]}))
        zf.writestr("autoplay-transcript.json", json.dumps([{"turn_index": 1}]))

    result = run_report_size_guard_from_argv(["--output-dir", str(tmp_path)])

    assert result["ok"] is True
    assert result["file_result"]["capped_files"]
    assert Path(result["summary_path"]).exists()
    assert json.loads(report.read_text(encoding="utf-8"))["source"] == SIZE_GUARD_SOURCE
    with zipfile.ZipFile(tmp_path / "autoplay-campaign-results.zip", "r") as zf:
        payload = json.loads(zf.read(REPORT_JSON_NAME).decode("utf-8"))
        transcript = json.loads(zf.read("autoplay-transcript.json").decode("utf-8"))
    assert payload["capped"] is True
    assert transcript == [{"turn_index": 1}]


def test_phase13_9_missing_output_dir_is_reported():
    result = run_report_size_guard_from_argv(["--turns", "100"])
    assert result["ok"] is False
    assert result["reason"] == "output_dir_not_found"
