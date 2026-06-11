from __future__ import annotations

import json
from pathlib import Path

from tests.rpg import interactive_cli_live_llm_stateful_stress_matrix as stress
from tests.rpg.interactive_cli_live_quality_eval import LIVE_QUALITY_EVAL_VERSION


def _transcript(text: str) -> dict:
    return {"turns": [{"turn_index": 1, "player_input": "test", "raw_narration": text, "narration_source": "provider_runtime_narration"}]}


def _judge_all_ok(**kwargs) -> dict:
    requirements = kwargs["requirements"]
    return {
        "ok": True,
        "requirements": {
            name: {"ok": True, "evidence": f"evidence for {name}", "reason": "visible stateful evidence"}
            for name in requirements
        },
        "reason": "all requirements satisfied",
    }


def _quality(turn_count: int = 4) -> dict:
    return {
        "format_version": LIVE_QUALITY_EVAL_VERSION,
        "ok": True,
        "turn_count": turn_count,
        "avg_score": 4.0,
        "scores": {"coherence": 4.0, "agency": 4.0, "specificity": 4.0, "continuity": 4.0, "fun": 4.0},
        "failures": [],
        "warnings": [],
        "signals": {},
    }


def test_phase14_11_stateful_stress_packs_are_registered() -> None:
    packs = stress.list_live_stateful_stress_packs()

    assert set(packs) == {
        "companion-memory-travel",
        "commerce-rest-ledger",
        "investigation-combat-aftermath",
        "travel-return-continuity",
    }
    assert any("red lantern" in command.lower() for command in packs["companion-memory-travel"])
    assert any("coin" in command.lower() for command in packs["commerce-rest-ledger"])
    assert any("wound" in command.lower() or "reward" in command.lower() for command in packs["investigation-combat-aftermath"])
    assert any("return" in command.lower() for command in packs["travel-return-continuity"])


def test_phase14_11_llm_judge_requires_multiple_stateful_requirements() -> None:
    result = stress.evaluate_live_stateful_stress_semantics(
        _transcript("Bran accompanies you on the old road and remembers the red lantern warning phrase."),
        pack="companion-memory-travel",
        semantic_judge_func=_judge_all_ok,
    )

    assert result["ok"] is True
    assert result["requirement_count"] == 3
    assert result["missing_count"] == 0
    assert result["judge"]["mode"] == "llm_judge"
    assert result["judge"]["valid"] is True
    assert set(result["matched"]) == {"companion_present", "seeded_memory_recalled", "travel_continuity"}


def test_phase14_11_llm_judge_failure_becomes_semantic_failure() -> None:
    def judge_missing_rest(**kwargs) -> dict:
        return {
            "ok": False,
            "requirements": {
                "service_price": {"ok": True, "evidence": "room costs silver", "reason": "price visible"},
                "payment_or_ledger": {"ok": True, "evidence": "coin checked", "reason": "ledger visible"},
                "rest_consequence": {"ok": False, "evidence": "", "reason": "no rest consequence visible"},
            },
            "reason": "missing rest consequence",
        }

    result = stress.evaluate_live_stateful_stress_semantics(
        _transcript("The room costs silver and you check your coin."),
        pack="commerce-rest-ledger",
        semantic_judge_func=judge_missing_rest,
    )

    assert result["ok"] is False
    assert result["missing_count"] == 1
    assert "stateful_semantic_commerce_rest_ledger_rest_consequence_missing" in result["failures"]


def test_phase14_11_invalid_judge_falls_back_to_deterministic_phrases() -> None:
    result = stress.evaluate_live_stateful_stress_semantics(
        _transcript("You leave the Rusty Flagon, mark a road fork, and note the path back for your return."),
        pack="travel-return-continuity",
        semantic_judge_func=lambda **kwargs: "not-json",
    )

    assert result["ok"] is True
    assert result["judge"]["mode"] == "deterministic_fallback"
    assert result["judge"]["used"] is True
    assert "stateful_semantic_llm_judge_fallback_used" in result["warnings"]


def test_phase14_11_matrix_runs_all_stateful_packs_and_aggregates(tmp_path: Path) -> None:
    captured: list[dict] = []

    def fake_runner(**kwargs):
        captured.append(dict(kwargs))
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = output_dir / "interactive-transcript.json"
        transcript_path.write_text(json.dumps(_transcript("provider narration")), encoding="utf-8")
        summary_path = Path(kwargs["summary_path"])
        summary_path.write_text(json.dumps(_quality(turn_count=len(kwargs["commands"]))), encoding="utf-8")
        return {"ok": True, "skipped": False, "transcript_path": str(transcript_path), "quality_summary_path": str(summary_path), "quality": _quality()}

    result = stress.run_live_stateful_stress_matrix(
        allow_live=True,
        output_dir=tmp_path / "stress",
        playtest_runner=fake_runner,
        semantic_judge_func=_judge_all_ok,
    )

    expected = sorted(stress.LIVE_STATEFUL_STRESS_PACKS)
    assert result["ok"] is True
    assert result["packs"] == expected
    assert [item["scenario_pack"] for item in captured] == expected
    assert all(item["scenario_pack"] == "" for item in captured)
    assert all(item["use_llm_semantic_judge"] is False for item in captured)
    assert result["aggregate"]["passed"] == len(expected)
    assert result["aggregate"]["failed"] == 0


def test_phase14_11_matrix_fails_when_stateful_semantics_fail(tmp_path: Path) -> None:
    def fake_runner(**kwargs):
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = output_dir / "interactive-transcript.json"
        transcript_path.write_text(json.dumps(_transcript("The room costs silver and you check your coin.")), encoding="utf-8")
        summary_path = Path(kwargs["summary_path"])
        summary_path.write_text(json.dumps(_quality()), encoding="utf-8")
        return {"ok": True, "skipped": False, "transcript_path": str(transcript_path), "quality_summary_path": str(summary_path), "quality": _quality()}

    def judge_missing_rest(**kwargs):
        return {
            "ok": False,
            "requirements": {
                "service_price": {"ok": True, "evidence": "room costs silver", "reason": "price visible"},
                "payment_or_ledger": {"ok": True, "evidence": "coin checked", "reason": "ledger visible"},
                "rest_consequence": {"ok": False, "evidence": "", "reason": "missing rest consequence"},
            },
            "reason": "missing rest consequence",
        }

    result = stress.run_live_stateful_stress_matrix(
        packs=["commerce-rest-ledger"],
        allow_live=True,
        output_dir=tmp_path / "stress",
        playtest_runner=fake_runner,
        semantic_judge_func=judge_missing_rest,
    )

    assert result["ok"] is False
    assert result["aggregate"]["failed"] == 1
    assert "stateful_semantic_commerce_rest_ledger_rest_consequence_missing" in result["aggregate"]["failure_types"]
    summary = json.loads(Path(result["summary_paths"][0]).read_text(encoding="utf-8"))
    assert summary["stateful_stress_semantics"]["missing_count"] == 1
    assert summary["signals"]["stateful_stress_judge_mode"] == "llm_judge"
