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
                "llm_called": True,
                "narration_source": "deferred_llm_narration",
                "interactive_cli_state_bundle": {"states": {"memory": {"facts": {"trail_name": "Ash Lantern"}}}},
            },
            {
                "turn_index": 2,
                "player_input": "I buy two rations for the trail.",
                "raw_narration": "Elara counts out two wrapped rations for your pack and names the silver cost before pointing toward the market gate. You can haggle, pay, or ask about road supplies.",
                "llm_called": True,
                "narration_source": "deferred_llm_narration",
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
    assert result["defer_runtime_narration"] is True
    assert result["drain_deferred_narration"] is True
    assert result["deferred_narration_drain"]["enabled"] is True
    assert result["quality"]["ok"] is True
    assert result["quality"]["signals"]["llm_narration_ratio"] == 1.0
    assert Path(result["quality_summary_path"]).exists()
    assert captured["turns"] == 2
    assert captured["scripted_commands"] == ["first", "second"]
    assert captured["reset_session"] is True
    assert captured["console_llm"] is False
    assert captured["seed_live_survival"] is True
    assert captured["enable_llm_intent_fallback"] is True
    assert captured["defer_runtime_narration"] is True
    assert callable(captured["after_turn_hook"])


def test_phase14_01_live_playtest_can_disable_deferred_runtime_narration_for_debug(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_runner(**kwargs):
        captured.update(kwargs)
        return {
            "summary": {"completed_turns": 1},
            "turns": [
                {
                    "turn_index": 1,
                    "player_input": "I ask Bran about the road.",
                    "raw_narration": "Bran points toward the old road and warns you about a bandit trail. Do you follow it?",
                    "llm_called": True,
                    "narration_source": "deferred_llm_narration",
                    "interactive_cli_state_bundle": {"states": {}},
                }
            ],
            "artifacts": {"transcript_path": str(tmp_path / "missing-transcript.json")},
        }

    result = playtest.run_live_llm_playtest(
        allow_live=True,
        output_dir=tmp_path / "out",
        defer_runtime_narration=False,
        campaign_runner=fake_runner,
    )

    assert result["defer_runtime_narration"] is False
    assert result["deferred_narration_drain"]["enabled"] is False
    assert captured["defer_runtime_narration"] is False
    assert captured["after_turn_hook"] is None


def test_phase14_02_live_playtest_drains_deferred_narration_before_quality_scoring(tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    completed_narration = (
        "Bran lowers his voice inside the Rusty Flagon, pointing you toward the old north road where "
        "bandit tracks cut through fresh mud. He gives you a clear choice: question Elara for supplies, "
        "follow the trail now, or ask the guard about recent attacks."
    )

    def fake_drain_func(**kwargs):
        return {
            "format_version": "rpg_narration_v2",
            "source": "provider_runtime_narration",
            "narration_status": "completed",
            "narration": completed_narration,
            "runtime_narration_diagnostics": {
                "provider_attempted": True,
                "provider_present": True,
                "provider_valid": True,
                "provider_errors": [],
            },
        }

    def fake_runner(**kwargs):
        captured.update(kwargs)
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        turn_summary = {
            "turn_index": 1,
            "player_input": "I ask Bran what danger remains nearby.",
            "raw_narration": "The moment responds without producing a major new consequence.",
            "llm_called": False,
            "narration_source": "deferred_runtime_narration_pending",
            "raw_narration_payload": {
                "source": "deferred_runtime_narration_pending",
                "narration_status": "pending",
                "narration": "The moment responds without producing a major new consequence.",
                "runtime_narration_diagnostics": {
                    "provider_attempted": False,
                    "provider_valid": False,
                },
            },
            "raw_result": {
                "ok": True,
                "llm_called": False,
                "narration_status": "queued",
                "narration_mode": "deferred",
                "narration": "The moment responds without producing a major new consequence.",
                "narration_payload": {
                    "source": "deferred_runtime_narration_pending",
                    "narration_status": "pending",
                    "narration": "The moment responds without producing a major new consequence.",
                },
                "result": {
                    "action_type": "observe",
                    "visible_interaction_reason": "road_danger_inquiry",
                },
                "turn_contract": {"player_input": "I ask Bran what danger remains nearby."},
                "npc": {"speaker": "Bran", "line": ""},
                "session": {
                    "runtime_state": {"current_scene": {"scene": "The Rusty Flagon tavern"}},
                    "simulation_state": {
                        "player_state": {
                            "location_id": "loc:rusty_flagon",
                            "nearby_npc_ids": ["npc:bran"],
                            "inventory_state": {"items": [], "currency": {"silver": 10}},
                        }
                    },
                },
            },
            "interactive_cli_state_bundle": {"states": {}},
        }
        kwargs["after_turn_hook"](
            session_id=kwargs["session_id"],
            turn_summary=turn_summary,
            turn_index=1,
            player_input=turn_summary["player_input"],
        )
        transcript_path = output_dir / "interactive-transcript.json"
        transcript_path.write_text(
            json.dumps(
                {
                    "format_version": "interactive_cli_campaign_v4",
                    "summary": {"completed_turns": 1},
                    "turns": [turn_summary],
                }
            ),
            encoding="utf-8",
        )
        return {
            "summary": {"completed_turns": 1},
            "turns": [turn_summary],
            "artifacts": {"transcript_path": str(transcript_path)},
        }

    result = playtest.run_live_llm_playtest(
        allow_live=True,
        output_dir=tmp_path / "out",
        commands=["I ask Bran what danger remains nearby."],
        campaign_runner=fake_runner,
        deferred_narration_drain_func=fake_drain_func,
    )

    transcript = json.loads(Path(result["transcript_path"]).read_text(encoding="utf-8"))
    turn = transcript["turns"][0]
    assert result["ok"] is True
    assert result["quality"]["ok"] is True
    assert result["quality"]["signals"]["llm_narration_ratio"] == 1.0
    assert result["deferred_narration_drain"]["pending_count"] == 1
    assert result["deferred_narration_drain"]["completed_count"] == 1
    assert result["deferred_narration_drain"]["timeout_count"] == 0
    assert turn["raw_narration"] == completed_narration
    assert turn["llm_called"] is True
    assert turn["narration_source"] == "provider_runtime_narration"
    assert turn["raw_narration_payload"]["narration_status"] == "completed"
    assert turn["raw_result"]["narration_payload"]["source"] == "provider_runtime_narration"
    assert captured["defer_runtime_narration"] is True
    assert callable(captured["after_turn_hook"])


def test_phase13_97_live_playtest_falls_back_to_campaign_result_when_transcript_missing(tmp_path: Path) -> None:
    def fake_runner(**kwargs):
        return {
            "summary": {"completed_turns": 1},
            "turns": [
                {
                    "turn_index": 1,
                    "player_input": "I ask Bran about the road.",
                    "raw_narration": "Bran points toward the old road and warns you about a bandit trail. Do you follow it?",
                    "llm_called": True,
                    "narration_source": "deferred_llm_narration",
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


def test_phase13_97_live_playtest_status_marker_reports_skip_error() -> None:
    marker = playtest.render_live_llm_playtest_status_marker(
        {
            "ok": False,
            "skipped": True,
            "error": "live_llm_playtest_not_enabled",
        }
    )

    assert marker == "[RPG_LIVE_LLM_PLAYTEST] ok=false skipped=true turn_count=0 avg_score=0.000 fun=0.000 error=live_llm_playtest_not_enabled"


def test_phase13_97_live_playtest_cli_returns_two_when_not_enabled(monkeypatch, capsys) -> None:
    monkeypatch.delenv(playtest.LIVE_LLM_PLAYTEST_ENV_FLAG, raising=False)

    assert playtest.main([]) == 2

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["skipped"] is True
    assert payload["error"] == "live_llm_playtest_not_enabled"
    assert output.err.strip() == "[RPG_LIVE_LLM_PLAYTEST] ok=false skipped=true turn_count=0 avg_score=0.000 fun=0.000 error=live_llm_playtest_not_enabled"


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
            "--scenario-pack",
            "tavern-memory",
            "--no-reset-session-state",
            "--console-llm",
            "--no-live-survival-seed",
            "--no-deferred-runtime-narration",
            "--no-drain-deferred-narration",
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
    assert captured["scenario_pack"] == "tavern-memory"
    assert captured["reset_session"] is False
    assert captured["console_llm"] is True
    assert captured["seed_live_survival"] is False
    assert captured["defer_runtime_narration"] is False
    assert captured["drain_deferred_narration"] is False
    assert captured["artifact_detail"] == "summary"
    assert captured["summary_path"] == str(tmp_path / "quality.json")


def test_phase13_98_lists_builtin_live_playtest_scenario_packs() -> None:
    packs = playtest.list_live_llm_playtest_scenario_packs()

    assert sorted(packs) == ["combat-tension", "commerce-travel", "tavern-memory"]
    assert packs["tavern-memory"][0] == "Bran, remember this: my trail name is Ash Lantern."
    assert any("two rations" in command for command in packs["commerce-travel"])
    assert any("bandit" in command for command in packs["combat-tension"])


def test_phase13_98_resolves_named_scenario_pack() -> None:
    assert playtest.resolve_live_llm_playtest_scenario_pack("commerce-travel") == list(
        playtest.LIVE_LLM_PLAYTEST_SCENARIO_PACKS["commerce-travel"]
    )


def test_phase13_98_rejects_unknown_scenario_pack() -> None:
    try:
        playtest.resolve_live_llm_playtest_scenario_pack("missing-pack")
    except ValueError as exc:
        assert str(exc) == "unknown_live_llm_playtest_scenario_pack:missing-pack;available=combat-tension, commerce-travel, tavern-memory"
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("expected unknown scenario pack to raise")


def test_phase13_98_scenario_pack_feeds_runner_when_no_explicit_commands(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_runner(**kwargs):
        captured.update(kwargs)
        return {
            "summary": {"completed_turns": 1},
            "turns": [
                {
                    "turn_index": 1,
                    "player_input": "I ask Elara what trail food she recommends for the north road.",
                    "raw_narration": "Elara recommends rations for the north road and asks whether you want to buy two before leaving town.",
                    "llm_called": True,
                    "narration_source": "deferred_llm_narration",
                }
            ],
            "artifacts": {"transcript_path": str(tmp_path / "missing-transcript.json")},
        }

    result = playtest.run_live_llm_playtest(
        allow_live=True,
        output_dir=tmp_path / "out",
        scenario_pack="commerce-travel",
        campaign_runner=fake_runner,
    )

    assert result["scenario_pack"] == "commerce-travel"
    assert result["commands"] == list(playtest.LIVE_LLM_PLAYTEST_SCENARIO_PACKS["commerce-travel"])
    assert captured["scripted_commands"] == list(playtest.LIVE_LLM_PLAYTEST_SCENARIO_PACKS["commerce-travel"])
    assert captured["turns"] == len(playtest.LIVE_LLM_PLAYTEST_SCENARIO_PACKS["commerce-travel"])
    assert captured["defer_runtime_narration"] is True


def test_phase13_98_explicit_commands_override_scenario_pack(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_runner(**kwargs):
        captured.update(kwargs)
        return {
            "summary": {"completed_turns": 1},
            "turns": [
                {
                    "turn_index": 1,
                    "player_input": "custom",
                    "raw_narration": "Bran follows the script command and offers a road choice.",
                    "llm_called": True,
                    "narration_source": "deferred_llm_narration",
                }
            ],
            "artifacts": {"transcript_path": str(tmp_path / "missing-transcript.json")},
        }

    result = playtest.run_live_llm_playtest(
        allow_live=True,
        output_dir=tmp_path / "out",
        commands=["custom"],
        scenario_pack="combat-tension",
        campaign_runner=fake_runner,
    )

    assert result["commands"] == ["custom"]
    assert captured["scripted_commands"] == ["custom"]


def test_phase13_98_script_file_overrides_scenario_pack(tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    script_path = tmp_path / "commands.txt"
    script_path.write_text("from script\n", encoding="utf-8")

    def fake_runner(**kwargs):
        captured.update(kwargs)
        return {
            "summary": {"completed_turns": 1},
            "turns": [
                {
                    "turn_index": 1,
                    "player_input": "from script",
                    "raw_narration": "Bran follows the script command and offers a road choice.",
                    "llm_called": True,
                    "narration_source": "deferred_llm_narration",
                }
            ],
            "artifacts": {"transcript_path": str(tmp_path / "missing-transcript.json")},
        }

    result = playtest.run_live_llm_playtest(
        allow_live=True,
        output_dir=tmp_path / "out",
        script_file=script_path,
        scenario_pack="combat-tension",
        campaign_runner=fake_runner,
    )

    assert result["commands"] == ["from script"]
    assert captured["scripted_commands"] == ["from script"]


def test_phase13_98_unknown_scenario_pack_returns_structured_error() -> None:
    result = playtest.run_live_llm_playtest(allow_live=True, scenario_pack="missing-pack")

    assert result == {
        "format_version": playtest.LIVE_LLM_PLAYTEST_VERSION,
        "ok": False,
        "skipped": False,
        "error": "unknown_live_llm_playtest_scenario_pack:missing-pack;available=combat-tension, commerce-travel, tavern-memory",
    }


def test_phase13_98_cli_lists_scenario_packs(capsys) -> None:
    assert playtest.main(["--list-scenario-packs"]) == 0

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert sorted(payload["scenario_packs"]) == ["combat-tension", "commerce-travel", "tavern-memory"]
    assert output.err == ""