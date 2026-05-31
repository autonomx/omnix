from __future__ import annotations

from app.rpg.session.combat_lifecycle import (
    BANDIT_DEFEAT_COPPER_REWARD,
    BANDIT_DEFEAT_XP_REWARD,
    build_combat_lifecycle_snapshot,
    build_combat_reward_result,
    build_enemy_damage_contract,
    build_enemy_turn_resolution,
    enrich_combat_lifecycle_result,
    player_hp_before_for_enemy_turn,
)
from app.rpg.session.interactive_fast_combat_result_hook import (
    normalize_interactive_fast_combat_result,
)


def _fast_combat_result(*, defeated: bool = False, tick: int = 2, hp_before_override: int | None = None) -> dict:
    hp_before = hp_before_override if hp_before_override is not None else (1 if defeated else 4)
    hp_after = 0 if defeated else max(0, hp_before - 1)
    return {
        "tick": tick,
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
    assert log[1]["player_damage_pending"] is False
    assert log[1]["player_state_mutated"] is True
    assert log[1]["authoritative_player_combat_hp"] is True
    assert log[1]["survival_state_mutated"] is False
    assert log[1]["enemy_damage_contract"]["schema"] == "enemy_damage_contract_v1"
    assert lifecycle["player_combat_hp"]["before"] == 10
    assert lifecycle["player_combat_hp"]["after"] == 9
    assert lifecycle["progression_hooks"]["xp_pending"] is False
    assert lifecycle["progression_hooks"]["loot_pending"] is False


def test_pr16_derives_authoritative_player_hp_from_combat_turn_index():
    assert player_hp_before_for_enemy_turn(turn_index=2) == 10
    assert player_hp_before_for_enemy_turn(turn_index=3) == 9
    assert player_hp_before_for_enemy_turn(turn_index=4) == 8


def test_pr161_derives_authoritative_player_hp_from_enemy_hp_before_when_turn_index_missing():
    assert player_hp_before_for_enemy_turn(turn_index=0, enemy_hp_before=4) == 10
    assert player_hp_before_for_enemy_turn(turn_index=0, enemy_hp_before=3) == 9
    assert player_hp_before_for_enemy_turn(turn_index=0, enemy_hp_before=2) == 8


def test_pr15_builds_nonlethal_enemy_damage_contract():
    contract = build_enemy_damage_contract(player_hp_before=1, damage_applied=5)

    assert contract["schema"] == "enemy_damage_contract_v1"
    assert contract["metadata_only"] is False
    assert contract["player_state_mutated"] is True
    assert contract["survival_state_mutated"] is False
    assert contract["damage_applied"] == 0
    assert contract["player_hp_before"] == 1
    assert contract["player_hp_after"] == 1
    assert contract["player_hp_delta"] == 0
    assert contract["nonlethal_guard"] is True
    assert contract["authoritative_player_combat_hp"] is True


def test_pr18_builds_deterministic_combat_reward_result():
    reward = build_combat_reward_result(target_id="enemy:road_bandit", target_name="bandit", turn_index=5)

    assert reward["schema"] == "combat_reward_result_v1"
    assert reward["source"] == "deterministic_combat_reward_v1"
    assert reward["resolved"] is True
    assert reward["xp_awarded"] == BANDIT_DEFEAT_XP_REWARD
    assert reward["loot_awarded"]["currency"]["copper"] == BANDIT_DEFEAT_COPPER_REWARD
    assert reward["promotion_pending"] is True


def test_pr14_builds_enemy_turn_resolution_from_pending_lifecycle():
    lifecycle = {
        "initiative": {
            "schema": "combat_initiative_v1",
            "next_actor_id": "enemy:road_bandit",
            "round_index": 3,
        },
        "enemy_turn": {
            "schema": "enemy_turn_skeleton_v1",
            "pending": True,
            "actor_id": "enemy:road_bandit",
        },
    }

    resolution = build_enemy_turn_resolution(lifecycle)

    assert resolution["schema"] == "enemy_turn_resolution_v1"
    assert resolution["source"] == "pr1_6_authoritative_player_combat_hp"
    assert resolution["resolved"] is True
    assert resolution["pending"] is False
    assert resolution["actor_id"] == "enemy:road_bandit"
    assert resolution["combat_log_entry"]["phase"] == "enemy_action"
    assert resolution["combat_log_entry"]["source"] == "deterministic_enemy_damage_contract_v1"
    assert resolution["combat_log_entry"]["damage_applied"] == 1
    assert resolution["player_damage_pending"] is False
    assert resolution["player_hp_before"] == 9
    assert resolution["player_hp_after"] == 8
    assert resolution["player_state_mutated"] is True
    assert resolution["survival_state_mutated"] is False


def test_pr161_builds_enemy_turn_resolution_from_enemy_hp_when_turn_index_missing():
    lifecycle = {
        "initiative": {
            "schema": "combat_initiative_v1",
            "next_actor_id": "enemy:road_bandit",
            "round_index": 1,
        },
        "enemy_turn": {
            "schema": "enemy_turn_skeleton_v1",
            "pending": True,
            "actor_id": "enemy:road_bandit",
        },
        "combat_log": [
            {
                "phase": "player_action",
                "target_hp_before": 3,
                "target_hp_after": 2,
            }
        ],
    }

    resolution = build_enemy_turn_resolution(lifecycle)

    assert resolution["player_hp_before"] == 9
    assert resolution["player_hp_after"] == 8


def test_pr18_defeat_lifecycle_resolves_combat_rewards():
    lifecycle = build_combat_lifecycle_snapshot(_fast_combat_result(defeated=True, tick=5))

    assert lifecycle["initiative"]["next_actor_id"] == ""
    assert lifecycle["initiative"]["turn_phase"] == "combat_complete"
    assert lifecycle["enemy_turn"]["pending"] is False
    assert lifecycle["enemy_turn"]["reason"] == "combat_ended"
    assert lifecycle["combat_log"][0]["defeated"] is True
    assert lifecycle["combat_log"][0]["combat_ended"] is True
    assert len(lifecycle["combat_log"]) == 1
    assert lifecycle["progression_hooks"]["xp_pending"] is False
    assert lifecycle["progression_hooks"]["loot_pending"] is False
    assert lifecycle["progression_hooks"]["resolved"] is True
    assert lifecycle["progression_hooks"]["xp_awarded"] == BANDIT_DEFEAT_XP_REWARD
    assert lifecycle["progression_hooks"]["loot_awarded"]["currency"]["copper"] == BANDIT_DEFEAT_COPPER_REWARD
    assert lifecycle["combat_reward_result"]["schema"] == "combat_reward_result_v1"
    assert lifecycle["combat_reward_result"]["source"] == "deterministic_combat_reward_v1"


def test_pr1_enriches_result_and_nested_payloads_with_lifecycle_metadata():
    enriched = enrich_combat_lifecycle_result(_fast_combat_result(tick=3, hp_before_override=3))

    assert enriched["combat_lifecycle"]["schema"] == "combat_lifecycle_v1"
    assert enriched["combat_log"][0]["damage_applied"] == 1
    assert enriched["combat_log"][1]["phase"] == "enemy_action"
    assert enriched["combat_log"][1]["player_hp_before"] == 9
    assert enriched["combat_log"][1]["player_hp_after"] == 8
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
    assert normalized["combat_log"][1]["player_state_mutated"] is True
    assert normalized["combat_log"][1]["survival_state_mutated"] is False
    assert normalized["result"]["combat_log"][0]["target_hp_after"] == 3
