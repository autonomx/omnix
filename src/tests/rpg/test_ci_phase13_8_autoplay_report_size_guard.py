import json
import zipfile
from pathlib import Path

from app.rpg.autoplay_report_size_guard import (
    REPORT_JSON_NAME,
    SIZE_GUARD_SOURCE,
    cap_oversized_autoplay_reports,
    cap_oversized_report_files,
    cap_oversized_report_zip,
)
from tests.rpg.autoplay.survival_report_writer_hook import run_autoplay_survival_report_writer_hook


def test_phase13_8_caps_oversized_report_files(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RPG_AUTOPLAY_MAX_REPORT_JSON_BYTES", "64")
    report = tmp_path / REPORT_JSON_NAME
    report.write_text(json.dumps({"turns": ["x" * 200]}), encoding="utf-8")

    result = cap_oversized_report_files(tmp_path)
    payload = json.loads(report.read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert result["capped_files"][0]["original_size_bytes"] > 64
    assert payload["capped"] is True
    assert payload["source"] == SIZE_GUARD_SOURCE
    assert payload["reason"] == "report_artifact_exceeded_size_limit"
    assert report.stat().st_size < 1024


def test_phase13_8_caps_oversized_report_zip_members(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RPG_AUTOPLAY_MAX_REPORT_JSON_BYTES", "64")
    zip_path = tmp_path / "autoplay-campaign-results.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(REPORT_JSON_NAME, json.dumps({"turns": ["x" * 200]}))
        zf.writestr("autoplay-transcript.json", json.dumps([{"turn_index": 1}]))

    result = cap_oversized_report_zip(zip_path)

    assert result["ok"] is True
    assert result["capped_members"][0]["member"] == REPORT_JSON_NAME
    with zipfile.ZipFile(zip_path, "r") as zf:
        report_payload = json.loads(zf.read(REPORT_JSON_NAME).decode("utf-8"))
        transcript_payload = json.loads(zf.read("autoplay-transcript.json").decode("utf-8"))
    assert report_payload["capped"] is True
    assert report_payload["source"] == SIZE_GUARD_SOURCE
    assert transcript_payload == [{"turn_index": 1}]


def test_phase13_8_size_guard_writes_summary(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RPG_AUTOPLAY_MAX_REPORT_JSON_BYTES", "64")
    (tmp_path / REPORT_JSON_NAME).write_text(json.dumps({"rows": ["x" * 200]}), encoding="utf-8")

    result = cap_oversized_autoplay_reports(tmp_path)

    assert result["ok"] is True
    summary_path = Path(result["summary_path"])
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["file_result"]["capped_files"]


def test_phase13_8_post_run_hook_returns_size_guard_result(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RPG_AUTOPLAY_MAX_REPORT_JSON_BYTES", "64")
    (tmp_path / REPORT_JSON_NAME).write_text(json.dumps({"rows": ["x" * 200]}), encoding="utf-8")
    (tmp_path / "autoplay-transcript.json").write_text(json.dumps([{"turn_index": 1}]), encoding="utf-8")
    with zipfile.ZipFile(tmp_path / "autoplay-campaign-results.zip", "w") as zf:
        zf.writestr(REPORT_JSON_NAME, json.dumps({"rows": ["x" * 200]}))

    result = run_autoplay_survival_report_writer_hook(
        script_path=Path("src/tests/rpg/autoplay_llm_campaign.py"),
        results_dir=tmp_path,
    )

    assert result["ok"] is True
    assert result["size_guard_result"]["ok"] is True
    assert result["size_guard_result"]["file_result"]["capped_files"]
    with zipfile.ZipFile(tmp_path / "autoplay-campaign-results.zip", "r") as zf:
        report_payload = json.loads(zf.read(REPORT_JSON_NAME).decode("utf-8"))
    assert report_payload["capped"] is True
