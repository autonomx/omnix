from __future__ import annotations

import json
from pathlib import Path

from tests.rpg import interactive_cli_live_llm_playtest as playtest


def _write_transcript(path: Path) -> None:
    payload = {
        "format_version": "interactive_cli_campaign_v4",
        "turns": [
            {
                "turn_index": 1,
                "player_input": "Bran, remember this: my trail name is Ash Lantern.",
                "raw_narration": "Bran nods behind the Rusty Flagon bar. Ash Lantern, he repeats, and warns you the north road carries fresh bandit tracks. What will you ask him next?",
                "interactive_cli_state_bundle": {"states": {"memory": {"facts": {"trail_name": "Ash Lantern"}}}},
            },
            {
                "turn_index": 2,
                "player_input": "I buy two rations for the trail.",
                "raw_narration": "Elara counts out two wrapped rations for your pack and names the silver cost before pointing toward the market gate. You can haggle, pay, or ask about road supplies.",
                "interactive_cli_commerce_state": {"last_purchase": "two rations"},
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_phase13_97_live_playtest_refuses_without_explicit_opt_in(monkeypatch) -> None:
    monkeypatch.delenv(playtest.LIVE_LLM_PLAYTEST_ENV_FLAG, raising=False)

    result = playtest.run_live_llm_playtest(allow_live=False)

    assert result == {
        "format_version": playtest.LIVE_LLM_PLAYTEST_VERSION,
        "ok": False,
        "skipped": True,
        "error": "live_llm_playtest_not_enabled",
        "required_env": playtest.LIVE_LLM_PLAYTEST_ENV_FLAG,
    }


def test_phase13_97_live_playtest_runs_campaign_and_evaluates_transcript(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_runner(**kwargs):
        captured.update(kwargs)
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = output_dir / "interactive-transcript.json"
        _write_transcript(transcript_path)
        return {
            "summary": {"completed_turns": 2},
            "turns": [],
            "artifacts": {"transcript_path": str(transcript_path), "zip_path": str(output_dir / "interactive-campaign-results.zip")},
        }

    result = playtest.run_live_llm_playtest(
        allow_live=True,
        run_id="quality-smoke",
        session_id="session-quality-smoke",
        output_dir=tmp_path / "out",
        commands=["first", "second"],
        campaign_runner=fake_runner,
    )

    assert result["format_version"] == playtest.LIVE_LLM_PLAYTEST_VERSION
    assert result["ok"] is True
    assert result["skipped"] is False
    assert result["run_id"] == "quality-smoke"
    assert result["session_id"] == "session-quality-smoke"
    assert result["turn_count"] == 2
    assert result["quality"]["ok"] is True
    assert Path(result["quality_summary_path"]).exists()
    assert captured["turns"] == 2
    assert captured["scripted_commands"] == ["first", "second"]
    assert captured["reset_session"] is True
    assert captured["console_llm"] is False
    assert captured["seed_live_survival"] is True
    assert captured["enable_llm_intent_fallback"] is True


def test_phase13_97_live_playtest_falls_back_to_campaign_result_when_transcript_missing(tmp_path: Path) -> None:
    def fake_runner(**kwargs):
        return {
            "summary": {"completed_turns": 1},
            "turns": [
                {
                    "turn_index": 1,
                    "player_input": "I ask Bran about the road.",
                    "raw_narration": "Bran points toward the old road and warns you about a bandit trail. Do you follow it?",
                    "interactive_cli_state_bundle": {"states": {}},
                }
            ],
            "artifacts": {"transcript_path": str(tmp_path / "missing-transcript.json")},
        }

    result = playtest.run_live_llm_playtest(allow_live=True, output_dir=tmp_path / "out", campaign_runner=fake_runner)

    assert result["ok"] is True
    assert result["turn_count"] == 1
    assert result["quality"]["turn_count"] == 1


def test_phase13_97_live_playtest_status_marker_reports_quality() -> None:
    marker = playtest.render_live_llm_playtest_status_marker(
        {
            "ok": True,
            "skipped": False,
            "quality": {"turn_count": 3, "avg_score": 4.125, "scores": {"fun": 3.75}},
        }
    )

    assert marker == "[RPG_LIVE_LLM_PLAYTEST] ok=true skipped=false turn_count=3 avg_score=4.125 fun=3.750 error=none"


def test_phase13_97_live_playtest_cli_returns_two_when_not_enabled(monkeypatch, capsys) -> None:
    monkeypatch.delenv(playtest.LIVE_LLM_PLAYTEST_ENV_FLAG, raising=False)

    assert playtest.main([]) == 2

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["skipped"] is True
    assert payload["error"] == "live_llm_playtest_not_enabled"
    assert "[RPG_LIVE_LLM_PLAYTEST]" in output.err


def test_phase13_97_live_playtest_cli_wires_options(monkeypatch, tmp_path: Path, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_run_live_llm_playtest(**kwargs):
        captured.update(kwargs)
        return {
            "format_version": playtest.LIVE_LLM_PLAYTEST_VERSION,
            "ok": True,
            "skipped": False,
            "turn_count": 1,
            "quality": {"turn_count": 1, "avg_score": 4.0, "scores": {"fun": 3.5}},
        }

    monkeypatch.setattr(playtest, "run_live_llm_playtest", fake_run_live_llm_playtest)

    assert playtest.main(
        [
            "--allow-live",
            "--turns",
            "1",
            "--session-id",
            "s1",
            "--run-id",
            "r1",
            "--output-dir",
            str(tmp_path / "out"),
            "--command",
            "Ask Bran about trouble.",
            "--no-reset-session-state",
            "--console-llm",
            "--no-live-survival-seed",
            "--artifact-detail",
            "summary",
            "--summary-path",
            str(tmp_path / "quality.json"),
        ]
    ) == 0

    output = capsys.readouterr()
    assert json.loads(output.out)["ok"] is True
    assert captured["allow_live"] is True
    assert captured["turns"] == 1
    assert captured["session_id"] == "s1"
    assert captured["run_id"] == "r1"
    assert captured["commands"] == ["Ask Bran about trouble."]
    assert captured["reset_session"] is False
    assert captured["console_llm"] is True
    assert captured["seed_live_survival"] is False
    assert captured["artifact_detail"] == "summary"
    assert captured["summary_path"] == str(tmp_path / "quality.json")
