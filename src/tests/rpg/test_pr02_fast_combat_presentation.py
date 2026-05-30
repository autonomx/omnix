from __future__ import annotations

from app.rpg.session import runtime
from app.rpg.session.fast_combat_presentation import (
    deterministic_fast_combat_payload,
    prefer_fast_combat_narration,
)
from app.rpg.session.fast_combat_presentation_hook import (
    force_install_fast_combat_presentation_hook_for_tests,
)


def _fast_combat_result() -> dict:
    return {
        "narration": "The confrontation remains tense, but no injury is resolved.",
        "combat_narration_payload": {
            "source": "deterministic_combat_fast_summary",
            "narration": "You hit the bandit for 1 damage. The bandit has 3 HP remaining.",
            "npc": {},
            "combat_delta": {
                "damage_applied": 1,
                "target_hp_before": 4,
                "target_hp_after": 3,
                "target_name": "bandit",
            },
        },
        "combat_narration_validation": {
            "ok": False,
            "warnings": ["combat_narration_skipped_for_fast_mode"],
        },
        "result": {
            "narration": "The confrontation remains tense, but no injury is resolved.",
        },
    }


def test_pr02_detects_deterministic_fast_combat_payload_with_delta():
    payload = deterministic_fast_combat_payload(_fast_combat_result())

    assert payload["source"] == "deterministic_combat_fast_summary"
    assert payload["combat_delta"]["damage_applied"] == 1
    assert "1 damage" in payload["narration"]


def test_pr02_prefer_fast_combat_narration_over_stale_fallback():
    narration = prefer_fast_combat_narration(
        _fast_combat_result(),
        fallback="The confrontation remains tense, but no injury is resolved.",
    )

    assert narration == "You hit the bandit for 1 damage. The bandit has 3 HP remaining."
    assert "no injury is resolved" not in narration


def test_pr02_runtime_final_presentation_prefers_fast_combat_delta_over_deferred_fallback():
    force_install_fast_combat_presentation_hook_for_tests(runtime)

    selection = runtime._select_final_visible_presentation(
        _fast_combat_result(),
        runtime_narration_payload={
            "source": "deferred_runtime_narration_pending",
            "narration": "The confrontation remains tense, but no injury is resolved.",
            "npc": {},
        },
        prior_narration="The confrontation remains tense, but no injury is resolved.",
        prior_npc={},
        prior_llm_called=False,
    )

    assert selection["source"] == "deterministic_combat_fast_summary"
    assert selection["llm_called"] is False
    assert selection["runtime_payload_source"] == "deferred_runtime_narration_pending"
    assert selection["combat_delta"]["damage_applied"] == 1
    assert selection["narration"] == "You hit the bandit for 1 damage. The bandit has 3 HP remaining."
    assert "no injury is resolved" not in selection["narration"]
