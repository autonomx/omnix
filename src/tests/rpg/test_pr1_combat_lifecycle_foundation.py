from __future__ import annotations

from app.rpg.session.combat_lifecycle import (
    build_combat_lifecycle_snapshot,
    build_enemy_damage_contract,
    build_enemy_turn_resolution,
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
    assert lifecycle["initiative"]["next_actor_id"] == "player"
    assert lifecycle["initiative"]["turn_phase"] == "player_turn_ready"
    assert lifecycle["enemy_turn"]["pending"] is False
    assert lifecycle["enemy_turn"]["resolved"] is True
    assert lifecycle["enemy_turn"]["actor_id"] == "enemy:road_bandit"

    log = lifecycle["combat_log"]
    assert len(log) == 2
    assert log[0]["schema"] == "combat_log_entry_v1"
    assert log[0]["actor_id"] == "player"
    assert log[0]["target_id"] == "enemy:road_bandit"
    assert log[0]["damage_applied"] == 1
    assert log[0]["target_hp_before"] == 4
    assert log[0]["target_hp_after"] == 3
    assert log[0]["defeated"] is False
    assert log[1]["phase"] == "enemy_action"
    assert log[1]["source"] == "deterministic_enemy_damage_contract_v1"
    assert log[1]["actor_id"] == "enemy:road_bandit"
    assert log[1]["target_id"] == "player"
    assert log[1]["damage_applied"] == 1
    assert log[1]["target_hp_before"] == 10
    assert log[1]["target_hp_after"] == 9
    assert log[1]["player_damage_pending"] is True
    assert log[1]["player_state_mutated"] is False
    assert log[1]["enemy_damage_contract"]["schema"] == "enemy_damage_contract_v1"
    assert lifecycle["progression_hooks"]["xp_pending"] is False
    assert lifecycle["progression_hooks"]["loot_pending"] is False


def test_pr15_builds_nonlethal_enemy_damage_contract():
    contract = build_enemy_damage_contract(player_hp_before=1, damage_applied=5)

    assert contract["schema"] == "enemy_damage_contract_v1"
    assert contract["metadata_only"] is True
    assert contract["player_state_mutated"] is False
    assert contract["damage_applied"] == 0
    assert contract["player_hp_before"] == 1
    assert contract["player_hp_after"] == 1
    assert contract["player_hp_delta"] == 0
    assert contract["nonlethal_guard"] is True


def test_pr14_builds_enemy_turn_resolution_from_pending_lifecycle():
    lifecycle = {
        "initiative": {
            "schema": "combat_initiative_v1",
            "next_actor_id": "enemy:road_bandit",
            "round_index": 2,
        },
        "enemy_turn": {
            "schema": "enemy_turn_skeleton_v1",
            "pending": True,
            "actor_id": "enemy:road_bandit",
        },
    }

    resolution = build_enemy_turn_resolution(lifecycle)

    assert resolution["schema"] == "enemy_turn_resolution_v1"
    assert resolution["source"] == "pr1_5_enemy_damage_contract_v1"
    assert resolution["resolved"] is True
    assert resolution["pending"] is False
    assert resolution["actor_id"] == "enemy:road_bandit"
    assert resolution["combat_log_entry"]["phase"] == "enemy_action"
    assert resolution["combat_log_entry"]["source"] == "deterministic_enemy_damage_contract_v1"
    assert resolution["combat_log_entry"]["damage_applied"] == 1
    assert resolution["player_damage_pending"] is True
    assert resolution["player_hp_before"] == 10
    assert resolution["player_hp_after"] == 9
    assert resolution["player_state_mutated"] is False


def test_pr1_defeat_lifecycle_marks_combat_complete_and_progression_pending():
    lifecycle = build_combat_lifecycle_snapshot(_fast_combat_result(defeated=True))

    assert lifecycle["initiative"]["next_actor_id"] == ""
    assert lifecycle["initiative"]["turn_phase"] == "combat_complete"
    assert lifecycle["enemy_turn"]["pending"] is False
    assert lifecycle["enemy_turn"]["reason"] == "combat_ended"
    assert lifecycle["combat_log"][0]["defeated"] is True
    assert lifecycle["combat_log"][0]["combat_ended"] is True
    assert len(lifecycle["combat_log"]) == 1
    assert lifecycle["progression_hooks"]["xp_pending"] is True
    assert lifecycle["progression_hooks"]["loot_pending"] is True
    assert lifecycle["progression_hooks"]["resolved"] is False


def test_pr1_enriches_result_and_nested_payloads_with_lifecycle_metadata():
    enriched = enrich_combat_lifecycle_result(_fast_combat_result())

    assert enriched["combat_lifecycle"]["schema"] == "combat_lifecycle_v1"
    assert enriched["combat_log"][0]["damage_applied"] == 1
    assert enriched["combat_log"][1]["phase"] == "enemy_action"
    assert enriched["combat_log"][1]["player_hp_after"] == 9
    assert enriched["result"]["combat_lifecycle"]["initiative"]["turn_phase"] == "player_turn_ready"
    assert enriched["combat_narration_payload"]["combat_lifecycle"]["schema"] == "combat_lifecycle_v1"


def test_pr1_interactive_normalizer_preserves_fast_narration_and_adds_lifecycle():
    normalized = normalize_interactive_fast_combat_result(_fast_combat_result())

    assert normalized["narration_payload"]["source"] == "deterministic_combat_fast_summary"
    assert normalized["narration_payload"]["narration"] == "You hit the bandit for 1 damage. The bandit has 3 HP remaining."
    assert normalized["combat_lifecycle"]["initiative"]["turn_phase"] == "player_turn_ready"
    assert normalized["combat_lifecycle"]["enemy_turn"]["resolved"] is True
    assert normalized["combat_log"][0]["damage_applied"] == 1
    assert normalized["combat_log"][1]["phase"] == "enemy_action"
    assert normalized["combat_log"][1]["damage_applied"] == 1
    assert normalized["combat_log"][1]["player_state_mutated"] is False
    assert normalized["result"]["combat_log"][0]["target_hp_after"] == 3
