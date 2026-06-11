from __future__ import annotations

import json
from pathlib import Path

from tests.rpg import interactive_cli_live_llm_playtest as playtest


def _transcript(*narrations: str) -> dict:
    return {
        "turns": [
            {
                "turn_index": index,
                "player_input": f"scripted command {index}",
                "raw_narration": narration,
                "narration_source": "provider_runtime_narration",
                "narration_status": "completed",
                "llm_called": True,
                "interactive_cli_state_bundle": {"ok": True},
            }
            for index, narration in enumerate(narrations, start=1)
        ]
    }


def test_phase14_10_llm_judge_accepts_semantic_equivalent_without_keyword() -> None:
    def fake_judge(**kwargs):
        assert kwargs["scenario_pack"] == "party-companion"
        assert "companion_or_party" in kwargs["requirements"]
        return {
            "ok": True,
            "requirements": {
                "companion_or_party": {
                    "ok": True,
                    "evidence": "Bran says he will keep his shield at your back.",
                    "reason": "The line indicates Bran is joining the player as support.",
                }
            },
            "reason": "Companion mechanic is visible.",
        }

    result = playtest.evaluate_live_mechanic_semantics(
        _transcript("Bran nods. You will have my shield at your back, he says."),
        scenario_pack="party-companion",
        semantic_judge_func=fake_judge,
    )

    assert result["ok"] is True
    assert result["missing_count"] == 0
    assert result["failures"] == []
    assert result["judge"]["mode"] == "llm_judge"
    assert result["judge"]["valid"] is True
    assert result["matched"]["companion_or_party"]["evidence"]


def test_phase14_10_llm_judge_can_reject_generic_keyword_mentions() -> None:
    def fake_judge(**kwargs):
        return json.dumps(
            {
                "ok": False,
                "requirements": {
                    "companion_or_party": {
                        "ok": False,
                        "evidence": "The word party appears only as atmosphere, not as a joined companion state.",
                        "reason": "No one agrees to travel with or accompany the player.",
                    }
                },
                "reason": "The mechanic is not actually visible.",
            }
        )

    result = playtest.evaluate_live_mechanic_semantics(
        _transcript("The tavern party is loud, but Bran stays behind the bar."),
        scenario_pack="party-companion",
        semantic_judge_func=fake_judge,
    )

    assert result["ok"] is False
    assert result["failures"] == ["semantic_party_companion_companion_or_party_missing"]
    assert result["judge"]["mode"] == "llm_judge"
    assert result["matched"]["companion_or_party"]["reason"]


def test_phase14_10_invalid_llm_judge_falls_back_to_deterministic_phrases() -> None:
    def invalid_judge(**kwargs):
        return "not json"

    result = playtest.evaluate_live_mechanic_semantics(
        _transcript("Bran nods solemnly. Agreed. I will accompany you."),
        scenario_pack="party-companion",
        semantic_judge_func=invalid_judge,
    )

    assert result["ok"] is True
    assert result["missing_count"] == 0
    assert result["judge"]["mode"] == "deterministic_fallback"
    assert result["judge"]["used"] is True
    assert "semantic_llm_judge_fallback_used" in result["warnings"]
    assert result["matched"]["companion_or_party"]["matched_phrase"] == "accompany"


def test_phase14_10_run_live_playtest_writes_llm_judge_summary(tmp_path: Path) -> None:
    output_dir = tmp_path / "playtest"

    def fake_campaign_runner(**kwargs):
        transcript_path = Path(kwargs["output_dir"]) / "interactive-transcript.json"
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        transcript_path.write_text(
            json.dumps(_transcript("Bran says he will keep his shield at your back.")),
            encoding="utf-8",
        )
        return {"summary": {}, "artifacts": {"transcript_path": str(transcript_path)}}

    def fake_judge(**kwargs):
        return {
            "ok": True,
            "requirements": {
                "companion_or_party": {
                    "ok": True,
                    "evidence": "shield at your back",
                    "reason": "Bran visibly offers companion support.",
                }
            },
            "reason": "ok",
        }

    result = playtest.run_live_llm_playtest(
        allow_live=True,
        scenario_pack="party-companion",
        output_dir=output_dir,
        campaign_runner=fake_campaign_runner,
        semantic_judge_func=fake_judge,
    )

    quality = json.loads((output_dir / "live-quality-summary.json").read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert quality["mechanic_semantics"]["judge"]["mode"] == "llm_judge"
    assert quality["signals"]["mechanic_semantic_judge_mode"] == "llm_judge"
    assert quality["signals"]["mechanic_semantic_judge_valid"] is True
