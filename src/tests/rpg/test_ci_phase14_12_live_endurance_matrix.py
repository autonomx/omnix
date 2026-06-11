from __future__ import annotations

import json
from pathlib import Path

from tests.rpg import interactive_cli_live_llm_endurance_matrix as endurance
from tests.rpg.interactive_cli_live_quality_eval import LIVE_QUALITY_EVAL_VERSION


def _transcript(text: str) -> dict:
    return {"turns": [{"turn_index": 1, "player_input": "test", "raw_narration": text, "narration_source": "provider_runtime_narration"}]}


def _judge_all_ok(**kwargs) -> dict:
    requirements = kwargs["requirements"]
    return {
        "ok": True,
        "requirements": {
            name: {"ok": True, "evidence": f"evidence for {name}", "reason": "visible endurance evidence"}
            for name in requirements
        },
        "reason": "all requirements satisfied",
    }


def _quality(turn_count: int = 25) -> dict:
    return {
        "format_version": LIVE_QUALITY_EVAL_VERSION,
        "ok": True,
        "turn_count": turn_count,
        "avg_score": 4.0,
        "scores": {"coherence": 4.0, "agency": 4.0, "specificity": 4.0, "continuity": 4.0, "fun": 4.0},
        "failures": [],
        "warnings": [],
        "signals": {"llm_narration_ratio": 1.0, "visible_repair_turn_ratio": 0.0},
    }


def test_phase14_12_endurance_packs_are_registered_and_25_turns() -> None:
    packs = endurance.list_live_endurance_packs()

    assert set(packs) == {
        "companion-quest-economy-25",
        "combat-travel-aftermath-25",
        "memory-social-world-25",
    }
    assert all(len(commands) == 25 for commands in packs.values())
    assert any("blue candle" in command.lower() for command in packs["companion-quest-economy-25"])
    assert any("xp" in command.lower() or "reward" in command.lower() for command in packs["combat-travel-aftermath-25"])
    assert any("silver owl" in command.lower() for command in packs["memory-social-world-25"])


def test_phase14_12_llm_judge_requires_integrated_endurance_requirements() -> None:
    result = endurance.evaluate_live_endurance_semantics(
        _transcript("Bran accompanies you, coin changed, the bandit clue leads to the quarry, and he recalls blue candle."),
        pack="companion-quest-economy-25",
        semantic_judge_func=_judge_all_ok,
    )

    assert result["ok"] is True
    assert result["requirement_count"] == 4
    assert result["missing_count"] == 0
    assert result["judge"]["mode"] == "llm_judge"
    assert result["judge"]["valid"] is True
    assert set(result["matched"]) == {
        "companion_continuity",
        "economy_or_service_consequence",
        "quest_clue_continuity",
        "seeded_memory_recall",
    }


def test_phase14_12_llm_judge_failure_becomes_endurance_failure() -> None:
    def judge_missing_secret(**kwargs) -> dict:
        return {
            "ok": False,
            "requirements": {
                "private_memory_recall": {"ok": True, "evidence": "Bran recalls silver owl", "reason": "memory visible"},
                "social_rumor_continuity": {"ok": True, "evidence": "local rumor persists", "reason": "social thread visible"},
                "location_world_continuity": {"ok": True, "evidence": "return path to tavern", "reason": "location visible"},
                "secret_handling": {"ok": False, "evidence": "", "reason": "no protection of the secret"},
            },
            "reason": "missing secret handling",
        }

    result = endurance.evaluate_live_endurance_semantics(
        _transcript("Bran recalls silver owl and the local rumor while you return to the tavern."),
        pack="memory-social-world-25",
        semantic_judge_func=judge_missing_secret,
    )

    assert result["ok"] is False
    assert result["missing_count"] == 1
    assert "endurance_semantic_memory_social_world_25_secret_handling_missing" in result["failures"]


def test_phase14_12_invalid_judge_falls_back_to_deterministic_phrases() -> None:
    result = endurance.evaluate_live_endurance_semantics(
        _transcript("The fight is resolved, a wound changes your objective, and the road route returns to the Rusty Flagon."),
        pack="combat-travel-aftermath-25",
        semantic_judge_func=lambda **kwargs: "not-json",
    )

    assert result["ok"] is True
    assert result["judge"]["mode"] == "deterministic_fallback"
    assert result["judge"]["used"] is True
    assert "live_endurance_semantic_llm_judge_fallback_used" in result["warnings"]


def test_phase14_12_matrix_runs_all_endurance_packs_and_aggregates(tmp_path: Path) -> None:
    captured: list[dict] = []

    def fake_runner(**kwargs):
        captured.append(dict(kwargs))
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = output_dir / "interactive-transcript.json"
        transcript_path.write_text(json.dumps(_transcript("provider narration")), encoding="utf-8")
        summary_path = Path(kwargs["summary_path"])
        summary_path.write_text(json.dumps(_quality(turn_count=len(kwargs["commands"]))), encoding="utf-8")
        return {"ok": True, "skipped": False, "transcript_path": str(transcript_path), "quality_summary_path": str(summary_path), "quality": _quality(turn_count=len(kwargs["commands"]))}

    result = endurance.run_live_endurance_matrix(
        allow_live=True,
        output_dir=tmp_path / "endurance",
        playtest_runner=fake_runner,
        semantic_judge_func=_judge_all_ok,
    )

    expected = sorted(endurance.LIVE_ENDURANCE_PACKS)
    assert result["ok"] is True
    assert result["packs"] == expected
    assert [item["scenario_pack"] for item in captured] == expected
    assert all(len(item["commands"]) == 25 for item in captured)
    assert all(item["scenario_pack"] == "" for item in captured)
    assert all(item["use_llm_semantic_judge"] is False for item in captured)
    assert result["aggregate"]["passed"] == len(expected)
    assert result["aggregate"]["failed"] == 0
    assert result["aggregate"]["expected_summary_count"] == len(expected)
    assert result["aggregate"]["missing_summary_count"] == 0


def test_phase14_12_matrix_fails_when_endurance_semantics_fail(tmp_path: Path) -> None:
    def fake_runner(**kwargs):
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = output_dir / "interactive-transcript.json"
        transcript_path.write_text(json.dumps(_transcript("Bran recalls silver owl and the local rumor while you return to the tavern.")), encoding="utf-8")
        summary_path = Path(kwargs["summary_path"])
        summary_path.write_text(json.dumps(_quality()), encoding="utf-8")
        return {"ok": True, "skipped": False, "transcript_path": str(transcript_path), "quality_summary_path": str(summary_path), "quality": _quality()}

    def judge_missing_secret(**kwargs):
        return {
            "ok": False,
            "requirements": {
                "private_memory_recall": {"ok": True, "evidence": "Bran recalls silver owl", "reason": "memory visible"},
                "social_rumor_continuity": {"ok": True, "evidence": "local rumor persists", "reason": "social thread visible"},
                "location_world_continuity": {"ok": True, "evidence": "return path to tavern", "reason": "location visible"},
                "secret_handling": {"ok": False, "evidence": "", "reason": "missing secret handling"},
            },
            "reason": "missing secret handling",
        }

    result = endurance.run_live_endurance_matrix(
        packs=["memory-social-world-25"],
        allow_live=True,
        output_dir=tmp_path / "endurance",
        playtest_runner=fake_runner,
        semantic_judge_func=judge_missing_secret,
    )

    assert result["ok"] is False
    assert result["aggregate"]["failed"] == 1
    assert "endurance_semantic_memory_social_world_25_secret_handling_missing" in result["aggregate"]["failure_types"]
    summary = json.loads(Path(result["summary_paths"][0]).read_text(encoding="utf-8"))
    assert summary["live_endurance_semantics"]["missing_count"] == 1
    assert summary["signals"]["live_endurance_judge_mode"] == "llm_judge"
