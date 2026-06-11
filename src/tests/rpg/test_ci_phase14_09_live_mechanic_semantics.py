from __future__ import annotations

import json
from pathlib import Path

from tests.rpg import interactive_cli_live_llm_playtest as playtest
from tests.rpg import interactive_cli_live_llm_playtest_matrix as matrix
from tests.rpg.interactive_cli_live_quality_eval import LIVE_QUALITY_EVAL_VERSION


def _base_quality(turn_count: int = 4) -> dict:
    return {
        "format_version": LIVE_QUALITY_EVAL_VERSION,
        "ok": True,
        "turn_count": turn_count,
        "avg_score": 4.0,
        "scores": {
            "coherence": 4.0,
            "agency": 4.0,
            "specificity": 4.0,
            "continuity": 4.0,
            "fun": 4.0,
        },
        "signals": {},
        "failures": [],
        "warnings": [],
        "turns": [],
    }


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


def test_phase14_09_semantic_assertions_pass_when_pack_mechanic_is_visible() -> None:
    result = playtest.evaluate_live_mechanic_semantics(
        _transcript(
            "Bran agrees to join as your companion and travel with the party for now.",
            "He lists the help he can offer on the road.",
        ),
        scenario_pack="party-companion",
        use_llm_judge=False,
    )

    assert result["ok"] is True
    assert result["requirement_count"] == 1
    assert result["missing_count"] == 0
    assert result["failures"] == []
    assert result["matched"]["companion_or_party"]["matched_phrase"]
    assert result["judge"]["mode"] == "deterministic_fallback"


def test_phase14_09_semantic_assertions_fail_when_mechanic_is_missing() -> None:
    result = playtest.evaluate_live_mechanic_semantics(
        _transcript(
            "The tavern remains warm and the night outside is quiet.",
            "The innkeeper answers carefully, keeping his voice low.",
        ),
        scenario_pack="memory-recall-cross-scene",
        use_llm_judge=False,
    )

    assert result["ok"] is False
    assert result["missing_count"] == 1
    assert result["failures"] == ["semantic_memory_recall_cross_scene_memory_recall_missing"]


def test_phase14_09_semantic_failures_are_written_into_quality_summary(tmp_path: Path) -> None:
    output_dir = tmp_path / "playtest"

    def fake_campaign_runner(**kwargs):
        transcript_path = Path(kwargs["output_dir"]) / "interactive-transcript.json"
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        transcript_path.write_text(
            json.dumps(
                _transcript(
                    "The innkeeper smiles politely.",
                    "The hearth pops in the corner while conversation drifts elsewhere.",
                )
            ),
            encoding="utf-8",
        )
        return {
            "summary": {},
            "artifacts": {"transcript_path": str(transcript_path)},
        }

    result = playtest.run_live_llm_playtest(
        allow_live=True,
        scenario_pack="inn-service-economy",
        output_dir=output_dir,
        campaign_runner=fake_campaign_runner,
        use_llm_semantic_judge=False,
    )

    quality = json.loads((output_dir / "live-quality-summary.json").read_text(encoding="utf-8"))
    assert result["ok"] is False
    assert quality["ok"] is False
    assert "mechanic_semantics" in quality
    assert "semantic_inn_service_economy_service_payment_missing" in quality["failures"]
    assert quality["signals"]["mechanic_semantic_requirement_count"] == 1
    assert quality["signals"]["mechanic_semantic_missing_count"] == 1


def test_phase14_09_matrix_aggregate_fails_on_pack_semantic_failure(tmp_path: Path) -> None:
    output_dir = tmp_path / "matrix"

    def fake_runner(**kwargs):
        summary_path = Path(kwargs["summary_path"])
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        payload = _base_quality(turn_count=4)
        if kwargs["scenario_pack"] == "combat-resolution":
            semantics = playtest.evaluate_live_mechanic_semantics(
                _transcript("The road is quiet and no consequence is described."),
                scenario_pack="combat-resolution",
                use_llm_judge=False,
            )
            payload = playtest.apply_live_mechanic_semantics_to_quality(payload, semantics)
        summary_path.write_text(json.dumps(payload), encoding="utf-8")
        return {"ok": bool(payload["ok"]), "skipped": False, "quality_summary_path": str(summary_path), "quality": payload}

    result = matrix.run_live_llm_playtest_matrix(
        allow_live=True,
        output_dir=output_dir,
        scenario_packs=["combat-resolution", "party-companion"],
        playtest_runner=fake_runner,
    )

    assert result["ok"] is False
    assert result["aggregate"]["failed"] == 1
    assert "semantic_combat_resolution_combat_consequence_missing" in result["aggregate"]["failure_types"]
