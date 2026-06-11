from __future__ import annotations

import json
from pathlib import Path

from tests.rpg import interactive_cli_live_llm_playtest as playtest
from tests.rpg import interactive_cli_live_llm_playtest_matrix as matrix
from tests.rpg.interactive_cli_live_quality_eval import LIVE_QUALITY_EVAL_VERSION


EXPANDED_PACKS = {
    "party-companion",
    "quest-investigation",
    "inn-service-economy",
    "travel-encounter",
    "combat-resolution",
    "memory-recall-cross-scene",
}


def _passing_summary(turn_count: int) -> dict:
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
        "failures": [],
        "warnings": [],
    }


def test_phase14_08_expanded_runtime_packs_are_registered() -> None:
    packs = playtest.list_live_llm_playtest_scenario_packs()

    assert EXPANDED_PACKS.issubset(set(packs))
    assert any("companion" in command.lower() or "travel with me" in command.lower() for command in packs["party-companion"])
    assert any("clue" in command.lower() or "witness" in command.lower() for command in packs["quest-investigation"])
    assert any("price" in command.lower() or "room" in command.lower() for command in packs["inn-service-economy"])
    assert any("where i am" in command.lower() or "paths" in command.lower() for command in packs["travel-encounter"])
    assert any("reward" in command.lower() or "injury" in command.lower() for command in packs["combat-resolution"])
    assert any("blue ember" in command.lower() for command in packs["memory-recall-cross-scene"])


def test_phase14_08_matrix_defaults_include_expanded_runtime_packs() -> None:
    packs = matrix.resolve_live_llm_playtest_matrix_packs([])

    assert EXPANDED_PACKS.issubset(set(packs))
    assert packs == sorted(playtest.LIVE_LLM_PLAYTEST_SCENARIO_PACKS)


def test_phase14_08_matrix_runs_all_registered_packs_by_default(tmp_path: Path) -> None:
    captured: list[dict] = []

    def fake_runner(**kwargs):
        captured.append(dict(kwargs))
        summary_path = Path(kwargs["summary_path"])
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        turn_count = len(playtest.LIVE_LLM_PLAYTEST_SCENARIO_PACKS[kwargs["scenario_pack"]])
        payload = _passing_summary(turn_count=turn_count)
        summary_path.write_text(json.dumps(payload), encoding="utf-8")
        return {"ok": True, "skipped": False, "quality_summary_path": str(summary_path), "quality": payload}

    result = matrix.run_live_llm_playtest_matrix(
        allow_live=True,
        output_dir=tmp_path / "matrix",
        playtest_runner=fake_runner,
    )

    expected = sorted(playtest.LIVE_LLM_PLAYTEST_SCENARIO_PACKS)
    assert result["ok"] is True
    assert result["packs"] == expected
    assert result["pack_count"] == len(expected)
    assert [item["scenario_pack"] for item in captured] == expected
    assert {item["scenario_pack"] for item in captured}.issuperset(EXPANDED_PACKS)
    assert len(result["summary_paths"]) == len(expected)
    assert result["aggregate"]["passed"] == len(expected)
    assert result["aggregate"]["failed"] == 0
