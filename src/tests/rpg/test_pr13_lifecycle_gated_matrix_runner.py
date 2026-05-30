from __future__ import annotations

from types import SimpleNamespace

from tests.rpg import interactive_intent_matrix as matrix
from tests.rpg.interactive_intent_matrix_lifecycle_gate import apply_lifecycle_gate


def _lifecycle_turn(*, turn: int, before: int, after: int, defeated: bool = False) -> dict:
    damage = before - after
    lifecycle = {
        "schema": "combat_lifecycle_v1",
        "source": "pr1_combat_lifecycle_foundation",
        "initiative": {
            "schema": "combat_initiative_v1",
            "order": ["player", "enemy:road_bandit"],
            "active_actor_id": "player",
            "next_actor_id": "" if defeated else "enemy:road_bandit",
            "round_index": turn,
            "turn_phase": "combat_complete" if defeated else "awaiting_enemy_turn",
        },
        "enemy_turn": {
            "schema": "enemy_turn_skeleton_v1",
            "pending": not defeated,
            "actor_id": "" if defeated else "enemy:road_bandit",
            "reason": "combat_ended" if defeated else "enemy_turn_not_yet_resolved_in_pr1_foundation",
        },
        "combat_log": [
            {
                "schema": "combat_log_entry_v1",
                "entry_id": f"combat:test:{turn}",
                "turn_index": turn,
                "round_index": turn,
                "phase": "player_action",
                "actor_id": "player",
                "actor_side": "player",
                "target_id": "enemy:road_bandit",
                "target_name": "bandit",
                "target_side": "enemy",
                "action_type": "attack",
                "hit": damage > 0 or defeated,
                "damage_applied": damage,
                "target_hp_before": before,
                "target_hp_after": after,
                "defeated": defeated,
                "combat_ended": defeated,
                "source": "deterministic_combat_delta_contract_v1",
            }
        ],
        "progression_hooks": {
            "schema": "combat_progression_hooks_v1",
            "xp_pending": defeated,
            "loot_pending": defeated,
            "resolved": False,
            "reason": "placeholder_for_phase1_xp_loot_resolution",
        },
    }
    return {"turn_index": turn, "raw_result": {"combat_lifecycle": lifecycle}}


def _matrix_result(turns: list[dict], *, passed: int = 8) -> dict:
    return {
        "summary": {"passed": passed, "failed": [], "output_root": ""},
        "results": [
            {
                "scenario": SimpleNamespace(scenario_id=matrix.COMBAT_MATRIX_SCENARIO_ID),
                "result": {"turns": turns},
                "validation": {"ok": True, "failures": []},
            }
        ],
    }


def test_pr13_lifecycle_gate_passes_valid_combat_matrix_result():
    result = apply_lifecycle_gate(
        _matrix_result(
            [
                _lifecycle_turn(turn=2, before=4, after=3),
                _lifecycle_turn(turn=3, before=3, after=2),
                _lifecycle_turn(turn=4, before=2, after=1),
                _lifecycle_turn(turn=5, before=1, after=0, defeated=True),
            ]
        )
    )

    gate = result["summary"]["combat_lifecycle_gate"]
    assert gate["ok"] is True
    assert gate["failures"] == []
    assert result["summary"]["failed"] == []
    assert result["summary"]["passed"] == 8


def test_pr13_lifecycle_gate_marks_matrix_failed_when_lifecycle_missing():
    result = apply_lifecycle_gate(_matrix_result([{"turn_index": 2, "raw_result": {}}]))

    gate = result["summary"]["combat_lifecycle_gate"]
    assert gate["ok"] is False
    assert any("missing combat_lifecycle_v1" in failure for failure in gate["failures"])
    assert result["summary"]["failed"]
    assert result["summary"]["passed"] == 7


def test_pr13_lifecycle_gate_preserves_non_combat_matrix_results():
    result = {
        "summary": {"passed": 8, "failed": [], "output_root": ""},
        "results": [
            {
                "scenario": SimpleNamespace(scenario_id="commerce_food_purchase"),
                "result": {"turns": [{"turn_index": 1}]},
                "validation": {"ok": True, "failures": []},
            }
        ],
    }

    gated = apply_lifecycle_gate(result)

    assert gated["summary"]["combat_lifecycle_gate"]["ok"] is True
    assert gated["summary"]["combat_lifecycle_gate"]["failures"] == []
    assert gated["summary"]["failed"] == []
    assert gated["summary"]["passed"] == 8
