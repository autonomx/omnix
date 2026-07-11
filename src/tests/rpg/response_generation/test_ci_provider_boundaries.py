from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DETERMINISTIC_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "rpg-pr-deterministic.yml"


def test_deterministic_workflow_excludes_live_llm_autoplay() -> None:
    workflow = DETERMINISTIC_WORKFLOW.read_text(encoding="utf-8")

    assert "autoplay_llm_campaign" not in workflow
    assert "Real autoplay sample" not in workflow
    assert "RPG_AUTOPLAY_SKIP_FOREGROUND_LLM" not in workflow
    assert "RPG_AUTOPLAY_SKIP_COMBINED_BACKGROUND_LLM" not in workflow


def test_deterministic_workflow_keeps_provider_free_endurance_evidence() -> None:
    workflow = DETERMINISTIC_WORKFLOW.read_text(encoding="utf-8")

    assert "run_rpg_response_runtime_endurance.py" in workflow
    assert "--turns 1000" in workflow
    assert "Public apply-turn endurance" in workflow
    assert "deterministic-rpg-fast" in workflow
    assert "runtime-endurance" in workflow
