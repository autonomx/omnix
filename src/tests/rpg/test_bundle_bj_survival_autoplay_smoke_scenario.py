from __future__ import annotations

import json
import zipfile

from tests.rpg.autoplay.survival_smoke_scenario import (
    DEFAULT_SURVIVAL_SMOKE_ACTIONS,
    run_survival_smoke_sequence,
    write_survival_smoke_autoplay_artifacts,
)


def test_bundle_bj_survival_smoke_sequence_exercises_ticks_purchases_and_consumption() -> None:
    result = run_survival_smoke_sequence()

    assert result["ok"] is True
    rows = result["rows"]
    assert len(rows) == len(DEFAULT_SURVIVAL_SMOKE_ACTIONS)
    actions = [row["player_input"] for row in rows]
    assert actions == list(DEFAULT_SURVIVAL_SMOKE_ACTIONS)

    passive_rows = [row for row in rows if row["result"].get("survival_tick_result", {}).get("applied")]
    direct_rows = [row for row in rows if row["result"].get("survival_tick_result", {}).get("skipped")]
    assert passive_rows
    assert direct_rows
    assert any(row["result"]["survival_tick_result"]["reason"] == "travel_turn" for row in rows)

    survival_actions = [
        row["result"].get("resolved_result", {}).get("survival_result", {}).get("action")
        for row in rows
    ]
    assert "buy_water" in survival_actions
    assert "drink_water" in survival_actions
    assert "buy_rations" in survival_actions
    assert "eat_rations" in survival_actions

    final_survival = result["session"]["simulation_state"]["survival"]
    assert 0 <= final_survival["hunger"] <= 100
    assert 0 <= final_survival["thirst"] <= 100
    assert 0 <= final_survival["fatigue"] <= 100
    assert final_survival["events"]
    json.dumps(result)


def test_bundle_bj_smoke_artifacts_include_survival_metrics_json_html_and_zip_members(tmp_path) -> None:
    result = write_survival_smoke_autoplay_artifacts(tmp_path)

    assert result["ok"] is True
    transcript_path = tmp_path / "survival-smoke-transcript.json"
    zip_path = tmp_path / "autoplay-campaign-results.zip"
    metrics_json = tmp_path / "survival-report-metrics.json"
    metrics_html = tmp_path / "survival-report-metrics.html"
    assert transcript_path.exists()
    assert zip_path.exists()
    assert metrics_json.exists()
    assert metrics_html.exists()

    metrics = json.loads(metrics_json.read_text(encoding="utf-8"))
    assert metrics["summary"]["turns_observed"] >= len(DEFAULT_SURVIVAL_SMOKE_ACTIONS)
    assert metrics["summary"]["passive_tick_count"] >= 2
    assert metrics["summary"]["direct_survival_action_count"] >= 4
    assert metrics["action_counts"]["buy_water"] >= 1
    assert metrics["action_counts"]["drink_water"] >= 1
    assert metrics["action_counts"]["buy_rations"] >= 1
    assert metrics["action_counts"]["eat_rations"] >= 1
    assert "Survival Report Metrics" in metrics_html.read_text(encoding="utf-8")

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        assert "survival-smoke-transcript.json" in names
        assert "survival/survival-report-metrics.json" in names
        assert "survival/survival-report-metrics.html" in names
        zipped_metrics = json.loads(zf.read("survival/survival-report-metrics.json").decode("utf-8"))
    assert zipped_metrics["summary"]["direct_survival_action_count"] >= 4
    assert result["hook_result"]["ok"] is True
    assert result["hook_result"]["zip_result"]["ok"] is True
