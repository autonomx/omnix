import json
import zipfile
from pathlib import Path

from app.rpg.autoplay_performance_artifacts import (
    PERFORMANCE_SUMMARY_HTML_NAME,
    PERFORMANCE_SUMMARY_JSON_NAME,
    append_autoplay_performance_artifacts_to_zip,
    build_autoplay_performance_summary,
    write_autoplay_performance_artifacts,
)
from tests.rpg.autoplay.survival_report_writer_hook import run_autoplay_survival_report_writer_hook


def _slow_rows():
    return [
        {
            "turn_index": 1,
            "performance": {
                "wall_seconds": 17.0,
                "player_agent_seconds": 5.4,
                "runtime_seconds": 12.2,
                "background_seconds": 11.0,
            },
        },
        {
            "turn_index": 2,
            "timing": {
                "wall_seconds": 20.0,
                "player_agent_seconds": 6.1,
                "runtime_seconds": 13.1,
                "background_seconds": 12.0,
            },
        },
    ]


def test_phase13_2_performance_summary_flags_slow_smoke_shape():
    summary = build_autoplay_performance_summary(
        _slow_rows(),
        run_summary={"final_drain_seconds": 8.1},
    )

    assert summary["turns_observed"] == 2
    assert summary["summary"]["wall"]["avg_seconds"] == 18.5
    assert summary["summary"]["player_agent"]["avg_seconds"] == 5.75
    assert summary["summary"]["runtime"]["avg_seconds"] == 12.65
    assert summary["summary"]["final_drain_seconds"] == 8.1
    assert "avg_wall_seconds_above_target" in summary["warnings"]
    assert "avg_player_agent_seconds_above_target" in summary["warnings"]
    assert "avg_runtime_seconds_above_target" in summary["warnings"]
    assert "final_drain_seconds_above_target" in summary["warnings"]
    assert summary["advisory_only"] is True


def test_phase13_2_performance_artifacts_write_json_html_and_zip(tmp_path: Path):
    result = write_autoplay_performance_artifacts(tmp_path, _slow_rows())
    assert result["ok"] is True
    assert Path(result["json_path"]).name == PERFORMANCE_SUMMARY_JSON_NAME
    assert Path(result["html_path"]).name == PERFORMANCE_SUMMARY_HTML_NAME

    zip_path = tmp_path / "autoplay-campaign-results.zip"
    zip_result = append_autoplay_performance_artifacts_to_zip(zip_path, _slow_rows())
    assert zip_result["ok"] is True
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        assert f"performance/{PERFORMANCE_SUMMARY_JSON_NAME}" in names
        assert f"performance/{PERFORMANCE_SUMMARY_HTML_NAME}" in names
        payload = json.loads(zf.read(f"performance/{PERFORMANCE_SUMMARY_JSON_NAME}").decode("utf-8"))
    assert payload["summary"]["wall"]["avg_seconds"] == 18.5


def test_phase13_2_post_run_hook_attaches_performance_artifacts(tmp_path: Path):
    (tmp_path / "autoplay-transcript.json").write_text(json.dumps(_slow_rows()), encoding="utf-8")
    zip_path = tmp_path / "autoplay-campaign-results.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("autoplay-transcript.json", json.dumps(_slow_rows()))

    result = run_autoplay_survival_report_writer_hook(
        script_path=Path("src/tests/rpg/autoplay_llm_campaign.py"),
        results_dir=tmp_path,
    )

    assert result["ok"] is True
    assert result["performance_standalone_result"]["ok"] is True
    assert result["performance_zip_result"]["ok"] is True
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        assert f"performance/{PERFORMANCE_SUMMARY_JSON_NAME}" in names
        assert f"performance/{PERFORMANCE_SUMMARY_HTML_NAME}" in names
