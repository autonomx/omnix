import json
import shutil
import zipfile
from pathlib import Path

from app.rpg.autoplay_report_materialization_guard import (
    MATERIALIZATION_GUARD_SOURCE,
    SUMMARY_NAME,
    cap_report_materialization_bytes,
    install_report_materialization_size_guard,
)
from app.rpg.autoplay_report_size_guard import REPORT_JSON_NAME


def test_phase13_11_materialization_bytes_are_capped(monkeypatch):
    monkeypatch.setenv("RPG_AUTOPLAY_MAX_REPORT_JSON_BYTES", "64")
    payload = cap_report_materialization_bytes(REPORT_JSON_NAME, json.dumps({"rows": ["x" * 200]}).encode())
    decoded = json.loads(payload.decode("utf-8"))
    assert decoded["capped"] is True
    assert decoded["source"] == "autoplay_report_size_guard_v1"


def test_phase13_11_path_write_text_caps_after_materialization(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RPG_AUTOPLAY_MAX_REPORT_JSON_BYTES", "64")
    install_report_materialization_size_guard(output_dir=tmp_path)
    report = tmp_path / REPORT_JSON_NAME

    report.write_text(json.dumps({"rows": ["x" * 200]}), encoding="utf-8")

    capped = json.loads(report.read_text(encoding="utf-8"))
    summary = json.loads((tmp_path / SUMMARY_NAME).read_text(encoding="utf-8"))
    assert capped["capped"] is True
    assert summary["materialization_guard_source"] == MATERIALIZATION_GUARD_SOURCE
    assert summary["file_result"]["capped_files"]


def test_phase13_11_copyfile_caps_report_destination(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RPG_AUTOPLAY_MAX_REPORT_JSON_BYTES", "64")
    install_report_materialization_size_guard(output_dir=tmp_path)
    source = tmp_path / "source.json"
    destination = tmp_path / REPORT_JSON_NAME
    source.write_text(json.dumps({"rows": ["x" * 200]}), encoding="utf-8")

    shutil.copyfile(source, destination)

    capped = json.loads(destination.read_text(encoding="utf-8"))
    assert capped["capped"] is True
    assert (tmp_path / SUMMARY_NAME).exists()


def test_phase13_11_zip_writestr_caps_report_member(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RPG_AUTOPLAY_MAX_REPORT_JSON_BYTES", "64")
    install_report_materialization_size_guard(output_dir=tmp_path)
    zip_path = tmp_path / "autoplay-campaign-results.zip"

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(REPORT_JSON_NAME, json.dumps({"rows": ["x" * 200]}))
        zf.writestr("autoplay-transcript.json", json.dumps([{"turn_index": 1}]))

    with zipfile.ZipFile(zip_path, "r") as zf:
        capped = json.loads(zf.read(REPORT_JSON_NAME).decode("utf-8"))
        transcript = json.loads(zf.read("autoplay-transcript.json").decode("utf-8"))
    assert capped["capped"] is True
    assert transcript == [{"turn_index": 1}]
    summary = json.loads((tmp_path / SUMMARY_NAME).read_text(encoding="utf-8"))
    assert summary["zip_results"][0]["capped_members"]
