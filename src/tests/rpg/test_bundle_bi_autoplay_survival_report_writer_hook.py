from __future__ import annotations

import json
import zipfile
from pathlib import Path

from tests.rpg.autoplay.survival_report_writer_hook import (
    collect_survival_report_rows,
    find_latest_autoplay_zip,
    run_autoplay_survival_report_writer_hook,
)
from tests.rpg.autoplay_llm_campaign import _run_survival_report_writer_hook


def _row(turn: int):
    return {
        "turn": turn,
        "turn_contract": {
            "turn_id": f"turn:{turn}",
            "survival": {"hunger": 10 + turn, "thirst": 20 + turn, "fatigue": 30 + turn},
            "survival_pressure": {"hunger": "low", "thirst": "low", "fatigue": "moderate"},
            "survival_tick_result": {
                "applied": True,
                "reason": "standard_turn",
                "turn_id": f"turn:{turn}",
            },
        },
    }


def test_bundle_bi_collects_survival_rows_from_json_and_zip(tmp_path) -> None:
    (tmp_path / "summary.json").write_text(
        json.dumps({"turns": [_row(1)]}),
        encoding="utf-8",
    )
    zip_path = tmp_path / "autoplay-campaign-results.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("nested/transcript.json", json.dumps({"rows": [_row(2)]}))

    rows = collect_survival_report_rows(tmp_path, zip_path=zip_path)

    assert len(rows) >= 2
    assert any(row.get("turn") == 1 for row in rows)
    assert any(row.get("turn") == 2 for row in rows)


def test_bundle_bi_finds_latest_autoplay_zip(tmp_path) -> None:
    old_zip = tmp_path / "old-autoplay-campaign-results.zip"
    new_zip = tmp_path / "new-autoplay-campaign-results.zip"
    old_zip.write_bytes(b"placeholder")
    new_zip.write_bytes(b"placeholder")

    latest = find_latest_autoplay_zip(tmp_path)

    assert latest in {old_zip, new_zip}
    assert latest is not None
    assert latest.name.endswith("autoplay-campaign-results.zip")


def test_bundle_bi_hook_writes_standalone_and_zip_survival_artifacts(tmp_path) -> None:
    (tmp_path / "summary.json").write_text(
        json.dumps({"turns": [_row(1), _row(2)]}),
        encoding="utf-8",
    )
    zip_path = tmp_path / "autoplay-campaign-results.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("existing.txt", "ok")

    result = run_autoplay_survival_report_writer_hook(
        script_path=Path(__file__),
        argv=["--turns", "2"],
        exit_code=0,
        results_dir=tmp_path,
    )

    assert result["ok"] is True
    assert result["rows_observed"] >= 2
    assert (tmp_path / "survival-report-metrics.json").exists()
    assert (tmp_path / "survival-report-metrics.html").exists()
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        assert "survival/survival-report-metrics.json" in names
        assert "survival/survival-report-metrics.html" in names
        metrics = json.loads(zf.read("survival/survival-report-metrics.json").decode("utf-8"))
    assert metrics["summary"]["passive_tick_count"] >= 2


def test_bundle_bi_hook_is_idempotent_for_zip_members(tmp_path) -> None:
    (tmp_path / "summary.json").write_text(json.dumps({"turns": [_row(1)]}), encoding="utf-8")
    zip_path = tmp_path / "autoplay-campaign-results.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("existing.txt", "ok")

    first = run_autoplay_survival_report_writer_hook(
        script_path=Path(__file__),
        argv=[],
        exit_code=0,
        results_dir=tmp_path,
    )
    second = run_autoplay_survival_report_writer_hook(
        script_path=Path(__file__),
        argv=[],
        exit_code=0,
        results_dir=tmp_path,
    )

    assert first["ok"] is True
    assert second["ok"] is True
    assert second["zip_result"]["skipped"] is True
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
    assert names.count("survival/survival-report-metrics.json") == 1
    assert names.count("survival/survival-report-metrics.html") == 1


def test_bundle_bi_wrapper_hook_does_not_raise_without_results(tmp_path, capsys) -> None:
    # The stable autoplay wrapper calls this post-main.  It should only print a
    # compact diagnostic and must not raise when no autoplay ZIP exists yet.
    _run_survival_report_writer_hook(["--turns", "0"], 0)
    captured = capsys.readouterr()
    assert "AUTOPLAY-SURVIVAL-REPORT" in captured.out or "AUTOPLAY-SURVIVAL-REPORT" in captured.err
