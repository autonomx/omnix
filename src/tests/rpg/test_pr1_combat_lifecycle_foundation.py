from __future__ import annotations

from app.rpg.session.combat_lifecycle import (
    build_combat_lifecycle_snapshot,
    enrich_combat_lifecycle_result,
)
from app.rpg.session.interactive_fast_combat_result_hook import (
    normalize_interactive_fast_combat_result,
)


def _fast_combat_result(*, defeated: bool = False) -> dict:
    hp_before = 1 if defeated else 4
    hp_after = 0 if defeated else 3
    return {
        "tick": 2,
        "combat_narration_payload": {
            "source": "deterministic_combat_fast_summary",
            "narration": (
                "You hit the bandit for 1 damage and defeat them."
                if defeated
                else "You hit the bandit for 1 damage. The bandit has 3 HP remaining."
            ),
            "npc": {},
            "combat_delta": {
                "action_type": "attack",
                "actor_id": "player",
                "target_id": "enemy:road_bandit",
                "target_name": "bandit",
                "damage_applied": 1,
                "target_hp_before": hp_before,
                "target_hp_after": hp_after,
                "defeated": defeated,
                "combat_ended": defeated,
            },
        },
        "result": {},
    }


def test_pr1_builds_combat_lifecycle_snapshot_from_fast_combat_delta():
    lifecycle = build_combat_lifecycle_snapshot(_fast_combat_result())

    assert lifecycle["schema"] == "combat_lifecycle_v1"
    assert lifecycle["source"] == "pr1_combat_lifecycle_foundation"
    assert lifecycle["initiative"]["order"] == ["player", "enemy:road_bandit"]
    assert lifecycle["initiative"]["active_actor_id"] == "player"
    assert lifecycle["initiative"]["next_actor_id"] == "enemy:road_bandit"
    assert lifecycle["initiative"]["turn_phase"] == "awaiting_enemy_turn"
    assert lifecycle["enemy_turn"]["pending"] is True
    assert lifecycle["enemy_turn"]["actor_id"] == "enemy:road_bandit"

    log = lifecycle["combat_log"]
    assert len(log) == 1
    assert log[0]["schema"] == "combat_log_entry_v1"
    assert log[0]["actor_id"] == "player"
    assert log[0]["target_id"] == "enemy:road_bandit"
    assert log[0]["damage_applied"] == 1
    assert log[0]["target_hp_before"] == 4
    assert log[0]["target_hp_after"] == 3
    assert log[0]["defeated"] is False
    assert lifecycle["progression_hooks"]["xp_pending"] is False
    assert lifecycle["progression_hooks"]["loot_pending"] is False


def test_pr1_defeat_lifecycle_marks_combat_complete_and_progression_pending():
    lifecycle = build_combat_lifecycle_snapshot(_fast_combat_result(defeated=True))

    assert lifecycle["initiative"]["next_actor_id"] == ""
    assert lifecycle["initiative"]["turn_phase"] == "combat_complete"
    assert lifecycle["enemy_turn"]["pending"] is False
    assert lifecycle["enemy_turn"]["reason"] == "combat_ended"
    assert lifecycle["combat_log"][0]["defeated"] is True
    assert lifecycle["combat_log"][0]["combat_ended"] is True
    assert lifecycle["progression_hooks"]["xp_pending"] is True
    assert lifecycle["progression_hooks"]["loot_pending"] is True
    assert lifecycle["progression_hooks"]["resolved"] is False


def test_pr1_enriches_result_and_nested_payloads_with_lifecycle_metadata():
    enriched = enrich_combat_lifecycle_result(_fast_combat_result())

    assert enriched["combat_lifecycle"]["schema"] == "combat_lifecycle_v1"
    assert enriched["combat_log"][0]["damage_applied"] == 1
    assert enriched["result"]["combat_lifecycle"]["initiative"]["next_actor_id"] == "enemy:road_bandit"
    assert enriched["combat_narration_payload"]["combat_lifecycle"]["schema"] == "combat_lifecycle_v1"


def test_pr1_interactive_normalizer_preserves_fast_narration_and_adds_lifecycle():
    normalized = normalize_interactive_fast_combat_result(_fast_combat_result())

    assert normalized["narration_payload"]["source"] == "deterministic_combat_fast_summary"
    assert normalized["narration_payload"]["narration"] == "You hit the bandit for 1 damage. The bandit has 3 HP remaining."
    assert normalized["combat_lifecycle"]["initiative"]["turn_phase"] == "awaiting_enemy_turn"
    assert normalized["combat_log"][0]["damage_applied"] == 1
    assert normalized["result"]["combat_log"][0]["target_hp_after"] == 3
