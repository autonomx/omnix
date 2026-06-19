from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from app.rpg.autoplay_item_report_hook import (
    ITEM_AUTOPLAY_COVERAGE_HTML_NAME,
    ITEM_AUTOPLAY_COVERAGE_JSON_NAME,
    ITEM_AUTOPLAY_ENDURANCE_JSON_NAME,
    ITEM_AUTOPLAY_MANIFEST_JSON_NAME,
    ITEM_AUTOPLAY_REPORT_JSON_NAME,
    ITEM_AUTOPLAY_REPORT_ROWS_JSON_NAME,
    collect_item_autoplay_states,
    run_autoplay_item_report_hook,
)
from app.rpg.autoplay_report_size_guard import cap_oversized_autoplay_reports


def _state() -> dict[str, Any]:
    return {
        "current_turn": 100,
        "turn_count": 100,
        "metadata": {"genre": "classic_fantasy"},
        "player": {
            "inventory": [
                {"id": "ration", "item_id": "ration", "name": "Ration", "quantity": 2, "stackable": True},
                {"id": "field_knife", "item_id": "field_knife", "name": "Field Knife", "quantity": 1},
            ]
        },
        "mechanics": {
            "item_traces": [
                {"coverage_target": "pickup"},
                {"coverage_target": "use_effect"},
                {"coverage_target": "merchant"},
            ],
            "item_report_sections": [{"event": "item_report_generated"}],
        },
        "crafting": {"known_recipes": ["trail_ration"]},
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_collect_item_autoplay_states_from_directory_and_zip(tmp_path: Path) -> None:
    output_dir = tmp_path / "run"
    _write_json(output_dir / "autoplay-summary.json", {"summary": {"simulation_state": _state()}})
    zip_path = output_dir / "autoplay-campaign-results.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("summary.json", json.dumps({"game": _state()}))

    states = collect_item_autoplay_states(output_dir, zip_paths=[zip_path])

    assert states
    assert states[0]["player"]["inventory"]


def test_run_autoplay_item_report_hook_writes_files_and_zip_members(tmp_path: Path) -> None:
    output_dir = tmp_path / "run"
    _write_json(output_dir / "autoplay-summary.json", {"summary": {"simulation_state": _state()}})
    zip_path = output_dir / "autoplay-campaign-results.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("summary.json", json.dumps({"ok": True}))

    result = run_autoplay_item_report_hook(output_dir, zip_paths=[zip_path], total_turns=100)

    assert result["ok"] is True
    assert result["coverage_state_found"] is True
    assert (output_dir / ITEM_AUTOPLAY_REPORT_JSON_NAME).exists()
    assert (output_dir / ITEM_AUTOPLAY_REPORT_ROWS_JSON_NAME).exists()
    assert (output_dir / ITEM_AUTOPLAY_ENDURANCE_JSON_NAME).exists()
    assert (output_dir / ITEM_AUTOPLAY_MANIFEST_JSON_NAME).exists()
    assert (output_dir / ITEM_AUTOPLAY_COVERAGE_JSON_NAME).exists()
    assert (output_dir / ITEM_AUTOPLAY_COVERAGE_HTML_NAME).exists()
    coverage = json.loads((output_dir / ITEM_AUTOPLAY_COVERAGE_JSON_NAME).read_text(encoding="utf-8"))
    assert coverage["state_found"] is True
    assert coverage["latest_report"]["ok"] is True
    assert coverage["endurance_progress"]["covered_targets"] == ["merchant", "pickup", "use_effect"]
    with zipfile.ZipFile(zip_path, "r") as archive:
        names = set(archive.namelist())
    assert f"item/{ITEM_AUTOPLAY_REPORT_JSON_NAME}" in names
    assert f"item/{ITEM_AUTOPLAY_REPORT_ROWS_JSON_NAME}" in names
    assert f"item/{ITEM_AUTOPLAY_ENDURANCE_JSON_NAME}" in names
    assert f"item/{ITEM_AUTOPLAY_COVERAGE_JSON_NAME}" in names
    assert f"item/{ITEM_AUTOPLAY_COVERAGE_HTML_NAME}" in names
    assert f"item/{ITEM_AUTOPLAY_MANIFEST_JSON_NAME}" in names


def test_run_autoplay_item_report_hook_ignores_stale_generated_coverage(tmp_path: Path) -> None:
    output_dir = tmp_path / "run"
    _write_json(output_dir / ITEM_AUTOPLAY_COVERAGE_JSON_NAME, {"ok": False, "state_found": False})
    _write_json(output_dir / "autoplay-summary.json", {"summary": {"simulation_state": _state()}})

    result = run_autoplay_item_report_hook(output_dir, total_turns=100)

    assert result["ok"] is True
    coverage = json.loads((output_dir / ITEM_AUTOPLAY_COVERAGE_JSON_NAME).read_text(encoding="utf-8"))
    assert coverage["state_found"] is True
    assert coverage["latest_report"]["ok"] is True


def test_run_autoplay_item_report_hook_reports_missing_state(tmp_path: Path) -> None:
    output_dir = tmp_path / "run"
    output_dir.mkdir()
    _write_json(output_dir / "autoplay-summary.json", {"ok": True})

    result = run_autoplay_item_report_hook(output_dir)

    assert result["ok"] is False
    assert result["reason"] == "item_autoplay_state_not_found"


def test_size_guard_runs_item_report_hook_before_capping(tmp_path: Path) -> None:
    output_dir = tmp_path / "run"
    _write_json(output_dir / "autoplay-summary.json", {"summary": {"simulation_state": _state()}})
    zip_path = output_dir / "autoplay-campaign-results.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("summary.json", json.dumps({"ok": True}))

    result = cap_oversized_autoplay_reports(output_dir, zip_paths=[zip_path])

    assert result["ok"] is True
    assert result["item_autoplay_report"]["ok"] is True
    assert (output_dir / "autoplay-report-size-guard-summary.json").exists()
    with zipfile.ZipFile(zip_path, "r") as archive:
        names = set(archive.namelist())
    assert f"item/{ITEM_AUTOPLAY_REPORT_JSON_NAME}" in names
    assert f"item/{ITEM_AUTOPLAY_COVERAGE_JSON_NAME}" in names
