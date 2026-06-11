from __future__ import annotations

import json
from pathlib import Path

from tests.rpg import interactive_cli_live_llm_playtest_matrix as matrix
from tests.rpg.interactive_cli_live_quality_eval import LIVE_QUALITY_EVAL_VERSION


def _quality_summary(*, ok: bool = True, turn_count: int = 2, avg_score: float = 4.0, fun: float = 3.75, failures=None) -> dict:
    return {
        "format_version": LIVE_QUALITY_EVAL_VERSION,
        "ok": ok,
        "turn_count": turn_count,
        "avg_score": avg_score,
        "scores": {
            "coherence": avg_score,
            "agency": avg_score,
            "specificity": avg_score,
            "continuity": avg_score,
            "fun": fun,
        },
        "failures": list(failures or []),
        "warnings": [],
    }


def test_phase13_99_resolves_all_matrix_packs_by_default() -> None:
    assert matrix.resolve_live_llm_playtest_matrix_packs([]) == ["combat-tension", "commerce-travel", "tavern-memory"]


def test_phase13_99_resolves_selected_matrix_packs_without_duplicates() -> None:
    assert matrix.resolve_live_llm_playtest_matrix_packs(["commerce-travel", "commerce-travel", "tavern-memory"]) == [
        "commerce-travel",
        "tavern-memory",
    ]


def test_phase14_00_default_matrix_output_dir_is_under_resources_test_results() -> None:
    assert matrix.default_live_llm_playtest_matrix_output_dir() == Path(
        "resources/data/test-results/live-llm-playtest-matrix"
    )


def test_phase14_00_matrix_runner_defaults_to_resources_test_results(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_playtest_runner(**kwargs):
        summary_path = Path(kwargs["summary_path"])
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        payload = _quality_summary(ok=True, turn_count=1, avg_score=4.0, fun=4.0)
        summary_path.write_text(json.dumps(payload), encoding="utf-8")
        return {"ok": True, "skipped": False, "quality_summary_path": str(summary_path), "quality": payload}

    result = matrix.run_live_llm_playtest_matrix(
        scenario_packs=["tavern-memory"],
        allow_live=True,
        playtest_runner=fake_playtest_runner,
    )

    expected = Path("resources/data/test-results/live-llm-playtest-matrix")
    assert Path(result["output_dir"]) == expected
    assert Path(result["aggregate_path"]) == expected / "live-quality-aggregate.json"
    assert Path(result["summary_paths"][0]) == expected / "01-tavern-memory" / "live-quality-summary.json"


def test_phase13_99_matrix_runner_runs_selected_packs_and_aggregates(tmp_path: Path) -> None:
    captured: list[dict] = []

    def fake_playtest_runner(**kwargs):
        captured.append(dict(kwargs))
        summary_path = Path(kwargs["summary_path"])
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        payload = _quality_summary(ok=True, turn_count=3, avg_score=4.2, fun=3.9)
        summary_path.write_text(json.dumps(payload), encoding="utf-8")
        return {
            "ok": True,
            "skipped": False,
            "quality_summary_path": str(summary_path),
            "quality": payload,
        }

    result = matrix.run_live_llm_playtest_matrix(
        scenario_packs=["tavern-memory", "commerce-travel"],
        allow_live=True,
        output_dir=tmp_path / "matrix",
        turns=3,
        run_id_prefix="nightly",
        session_id_prefix="session-nightly",
        artifact_detail="summary",
        playtest_runner=fake_playtest_runner,
    )

    assert result["format_version"] == matrix.LIVE_LLM_PLAYTEST_MATRIX_VERSION
    assert result["ok"] is True
    assert result["skipped"] is False
    assert result["pack_count"] == 2
    assert result["packs"] == ["tavern-memory", "commerce-travel"]
    assert Path(result["aggregate_path"]).exists()
    assert len(result["summary_paths"]) == 2
    assert result["aggregate"]["passed"] == 2
    assert result["aggregate"]["failed"] == 0
    assert result["aggregate"]["total_turn_count"] == 6
    assert [item["scenario_pack"] for item in captured] == ["tavern-memory", "commerce-travel"]
    assert captured[0]["turns"] == 3
    assert captured[0]["run_id"] == "nightly-tavern-memory"
    assert captured[0]["session_id"] == "session-nightly_tavern-memory"
    assert captured[0]["artifact_detail"] == "summary"


def test_phase13_99_matrix_runner_reports_missing_summary(tmp_path: Path) -> None:
    def fake_playtest_runner(**kwargs):
        return {"ok": False, "skipped": False, "error": "runner_failed_before_summary"}

    result = matrix.run_live_llm_playtest_matrix(
        scenario_packs=["combat-tension"],
        allow_live=True,
        output_dir=tmp_path / "matrix",
        playtest_runner=fake_playtest_runner,
    )

    assert result["ok"] is False
    assert result["error"] == "live_llm_playtest_matrix_missing_summaries"
    assert result["missing_summary_count"] == 1
    assert result["aggregate"]["summary_count"] == 0


def test_phase13_99_matrix_runner_preserves_failed_quality_summary(tmp_path: Path) -> None:
    def fake_playtest_runner(**kwargs):
        summary_path = Path(kwargs["summary_path"])
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        payload = _quality_summary(ok=False, turn_count=2, avg_score=2.5, fun=2.0, failures=["average_quality_score_below_threshold"])
        summary_path.write_text(json.dumps(payload), encoding="utf-8")
        return {"ok": False, "skipped": False, "quality_summary_path": str(summary_path), "quality": payload}

    result = matrix.run_live_llm_playtest_matrix(
        scenario_packs=["combat-tension"],
        allow_live=True,
        output_dir=tmp_path / "matrix",
        playtest_runner=fake_playtest_runner,
    )

    assert result["ok"] is False
    assert result["aggregate"]["passed"] == 0
    assert result["aggregate"]["failed"] == 1
    assert result["aggregate"]["failure_types"] == ["average_quality_score_below_threshold"]
    assert result["runs"][0]["scenario_pack"] == "combat-tension"


def test_phase13_99_matrix_runner_reports_unknown_packs() -> None:
    result = matrix.run_live_llm_playtest_matrix(scenario_packs=["missing-pack"])

    assert result == {
        "format_version": matrix.LIVE_LLM_PLAYTEST_MATRIX_VERSION,
        "ok": False,
        "skipped": False,
        "error": "unknown_live_llm_playtest_matrix_pack",
        "unknown_packs": ["missing-pack"],
        "available_packs": ["combat-tension", "commerce-travel", "tavern-memory"],
    }


def test_phase13_99_matrix_status_marker_reports_aggregate() -> None:
    marker = matrix.render_live_llm_playtest_matrix_status_marker(
        {
            "ok": True,
            "skipped": False,
            "pack_count": 3,
            "aggregate": {
                "passed": 3,
                "failed": 0,
                "avg_score": 4.1234,
                "scores": {"fun": 3.8765},
            },
        }
    )

    assert marker == "[RPG_LIVE_LLM_PLAYTEST_MATRIX] ok=true skipped=false pack_count=3 passed=3 failed=0 avg_score=4.123 fun=3.877 error=none"


def test_phase13_99_matrix_cli_lists_packs(capsys) -> None:
    assert matrix.main(["--list-scenario-packs"]) == 0

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert sorted(payload["scenario_packs"]) == ["combat-tension", "commerce-travel", "tavern-memory"]
    assert output.err == ""


def test_phase13_99_matrix_cli_wires_options(monkeypatch, tmp_path: Path, capsys) -> None:
    captured: dict = {}

    def fake_run_matrix(**kwargs):
        captured.update(kwargs)
        return {
            "format_version": matrix.LIVE_LLM_PLAYTEST_MATRIX_VERSION,
            "ok": True,
            "skipped": False,
            "pack_count": 1,
            "aggregate": {"passed": 1, "failed": 0, "avg_score": 4.0, "scores": {"fun": 3.5}},
        }

    monkeypatch.setattr(matrix, "run_live_llm_playtest_matrix", fake_run_matrix)

    assert matrix.main(
        [
            "--allow-live",
            "--scenario-pack",
            "tavern-memory",
            "--turns",
            "2",
            "--output-dir",
            str(tmp_path / "out"),
            "--aggregate-path",
            str(tmp_path / "aggregate.json"),
            "--run-id-prefix",
            "rid",
            "--session-id-prefix",
            "sid",
            "--no-reset-session-state",
            "--console-llm",
            "--no-live-survival-seed",
            "--artifact-detail",
            "full",
        ]
    ) == 0

    output = capsys.readouterr()
    assert json.loads(output.out)["ok"] is True
    assert output.err.strip() == "[RPG_LIVE_LLM_PLAYTEST_MATRIX] ok=true skipped=false pack_count=1 passed=1 failed=0 avg_score=4.000 fun=3.500 error=none"
    assert captured["allow_live"] is True
    assert captured["scenario_packs"] == ["tavern-memory"]
    assert captured["turns"] == 2
    assert captured["output_dir"] == str(tmp_path / "out")
    assert captured["aggregate_path"] == str(tmp_path / "aggregate.json")
    assert captured["run_id_prefix"] == "rid"
    assert captured["session_id_prefix"] == "sid"
    assert captured["reset_session"] is False
    assert captured["console_llm"] is True
    assert captured["seed_live_survival"] is False
    assert captured["artifact_detail"] == "full"


def test_phase13_99_matrix_cli_returns_two_when_all_runs_skipped(monkeypatch, capsys) -> None:
    def fake_run_matrix(**kwargs):
        return {
            "format_version": matrix.LIVE_LLM_PLAYTEST_MATRIX_VERSION,
            "ok": False,
            "skipped": True,
            "pack_count": 1,
            "aggregate": {"passed": 0, "failed": 0, "avg_score": 0.0, "scores": {"fun": 0.0}},
            "error": "live_llm_playtest_not_enabled",
        }

    monkeypatch.setattr(matrix, "run_live_llm_playtest_matrix", fake_run_matrix)

    assert matrix.main(["--scenario-pack", "tavern-memory"]) == 2

    output = capsys.readouterr()
    assert json.loads(output.out)["skipped"] is True
    assert output.err.strip() == "[RPG_LIVE_LLM_PLAYTEST_MATRIX] ok=false skipped=true pack_count=1 passed=0 failed=0 avg_score=0.000 fun=0.000 error=live_llm_playtest_not_enabled"
