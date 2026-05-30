from __future__ import annotations

from app.rpg.session import runtime
from app.rpg.session.fast_combat_presentation import (
    deterministic_fast_combat_payload,
    prefer_fast_combat_narration,
    repair_fast_combat_grounding_validation,
)
from app.rpg.session.fast_combat_presentation_hook import (
    force_install_fast_combat_presentation_hook_for_tests,
)
from app.rpg.session.interactive_fast_combat_result_hook import (
    normalize_interactive_fast_combat_result,
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
        "narration_payload": {
            "source": "deferred_runtime_narration_pending",
            "narration": "The confrontation remains tense, but no injury is resolved.",
            "action": "No combat, damage, death, or injury is resolved by the turn contract.",
            "grounding_validation": {
                "ok": False,
                "fallback_used": True,
                "fallback_source": "deterministic_fallback",
                "selected_candidate": "deterministic_fallback",
                "violations": [{"code": "unsupported_combat_claim"}],
            },
        },
        "structured_narration": {
            "source": "deferred_runtime_narration_pending",
            "narration": "The confrontation remains tense, but no injury is resolved.",
            "grounding_validation": {
                "ok": False,
                "fallback_used": True,
                "fallback_source": "deterministic_fallback",
                "selected_candidate": "deterministic_fallback",
                "violations": [{"code": "unsupported_combat_claim"}],
            },
        },
        "result": {
            "narration": "The confrontation remains tense, but no injury is resolved.",
            "extracted": {
                "action": "No combat, damage, death, or injury is resolved by the turn contract.",
                "grounding_validation": {
                    "ok": False,
                    "fallback_used": True,
                    "fallback_source": "deterministic_fallback",
                    "selected_candidate": "deterministic_fallback",
                    "violations": [
                        {
                            "code": "unsupported_combat_claim",
                            "field": "narration",
                            "message": "Narration mentions combat/death/injury/blood/damage, but the turn contract has no combat delta.",
                        }
                    ],
                },
                "narration": "The confrontation remains tense, but no injury is resolved.",
            },
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


def test_pr03_fast_combat_grounding_repair_removes_false_unsupported_combat_claim():
    repaired = repair_fast_combat_grounding_validation(_fast_combat_result())
    validation = repaired["result"]["extracted"]["grounding_validation"]

    assert repaired["fast_combat_grounding_delta_repair"]["applied"] is True
    assert validation["ok"] is True
    assert validation["fallback_used"] is False
    assert validation["violations"] == []
    assert validation["fast_combat_delta_supported"] is True
    assert repaired["result"]["extracted"]["narration"] == "You hit the bandit for 1 damage. The bandit has 3 HP remaining."


def test_pr03_runtime_selector_repairs_grounding_validation_before_final_selection():
    force_install_fast_combat_presentation_hook_for_tests(runtime)
    result = _fast_combat_result()

    selection = runtime._select_final_visible_presentation(
        result,
        runtime_narration_payload={"source": "deferred_runtime_narration_pending", "narration": "pending"},
        prior_narration="The confrontation remains tense, but no injury is resolved.",
        prior_npc={},
        prior_llm_called=False,
    )

    validation = result["result"]["extracted"]["grounding_validation"]
    assert selection["source"] == "deterministic_combat_fast_summary"
    assert validation["ok"] is True
    assert validation["violations"] == []
    assert result["fast_combat_grounding_delta_repair"]["applied"] is True


def test_pr034_interactive_result_normalizer_restores_transcript_facing_payloads():
    normalized = normalize_interactive_fast_combat_result(_fast_combat_result())

    for key in ("narration_payload", "structured_narration"):
        payload = normalized[key]
        validation = payload["grounding_validation"]
        assert payload["source"] == "deterministic_combat_fast_summary"
        assert payload["narration"] == "You hit the bandit for 1 damage. The bandit has 3 HP remaining."
        assert validation["ok"] is True
        assert validation["violations"] == []
        assert normalized["grounding_violation_codes"] == []
