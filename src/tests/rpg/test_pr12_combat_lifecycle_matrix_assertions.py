from __future__ import annotations

from tests.rpg.combat_lifecycle_matrix_assertions import (
    combat_lifecycle_from_matrix_turn,
    validate_combat_lifecycle_matrix_turns,
)


def _enemy_action_row(*, turn: int, player_hp_before: int | None = None) -> dict:
    if player_hp_before is None:
        player_hp_before = max(1, 10 - max(0, turn - 2))
    player_hp_after = max(1, player_hp_before - 1)
    contract = {
        "schema": "enemy_damage_contract_v1",
        "source": "pr1_6_authoritative_player_combat_hp",
        "metadata_only": False,
        "player_state_mutated": True,
        "damage_applied": player_hp_before - player_hp_after,
        "player_hp_before": player_hp_before,
        "player_hp_after": player_hp_after,
        "player_damage_pending": False,
        "player_hp_delta": player_hp_after - player_hp_before,
        "nonlethal_guard": True,
        "authoritative_player_combat_hp": True,
        "survival_state_mutated": False,
    }
    return {
        "schema": "combat_log_entry_v1",
        "entry_id": f"combat:enemy:{turn}",
        "turn_index": turn,
        "round_index": turn,
        "phase": "enemy_action",
        "actor_id": "enemy:road_bandit",
        "actor_side": "enemy",
        "target_id": "player",
        "target_name": "player",
        "target_side": "player",
        "action_type": "counterattack",
        "hit": contract["damage_applied"] > 0,
        "damage_applied": contract["damage_applied"],
        "target_hp_before": player_hp_before,
        "target_hp_after": player_hp_after,
        "player_hp_before": player_hp_before,
        "player_hp_after": player_hp_after,
        "player_damage_pending": False,
        "player_hp_delta": player_hp_after - player_hp_before,
        "player_state_mutated": True,
        "authoritative_player_combat_hp": True,
        "survival_state_mutated": False,
        "defeated": False,
        "combat_ended": False,
        "source": "deterministic_enemy_damage_contract_v1",
        "enemy_damage_contract": contract,
    }


def _reward_result(*, turn: int) -> dict:
    return {
        "schema": "combat_reward_result_v1",
        "source": "deterministic_combat_reward_v1",
        "target_id": "enemy:road_bandit",
        "target_name": "bandit",
        "turn_index": turn,
        "resolved": True,
        "xp_awarded": 25,
        "loot_awarded": {"currency": {"copper": 7}, "items": []},
        "reward_lines": ["Gained 25 XP.", "Looted 7 copper."],
        "player_state_mutated": False,
        "inventory_state_mutated": False,
        "promotion_pending": True,
        "reason": "deterministic_bandit_defeat_reward_recorded_for_pr1_8",
    }


def _turn(*, turn: int, before: int, after: int, defeated: bool = False, resolved_enemy: bool = False) -> dict:
    damage = before - after
    combat_log = [
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
    ]
    if resolved_enemy:
        combat_log.append(_enemy_action_row(turn=turn))
    reward = _reward_result(turn=turn) if defeated else {}
    progression_hooks = {
        "schema": "combat_progression_hooks_v1",
        "xp_pending": False,
        "loot_pending": False,
        "resolved": bool(defeated),
        "reason": "combat_rewards_resolved_in_pr1_8" if defeated else "placeholder_for_phase1_xp_loot_resolution",
    }
    if defeated:
        progression_hooks.update(
            {
                "source": "deterministic_combat_reward_v1",
                "xp_awarded": reward["xp_awarded"],
                "loot_awarded": reward["loot_awarded"],
                "reward_result": reward,
            }
        )
    lifecycle = {
        "schema": "combat_lifecycle_v1",
        "source": "pr1_combat_lifecycle_foundation",
        "initiative": {
            "schema": "combat_initiative_v1",
            "order": ["player", "enemy:road_bandit"],
            "active_actor_id": "player",
            "next_actor_id": "" if defeated else ("player" if resolved_enemy else "enemy:road_bandit"),
            "round_index": turn,
            "turn_phase": "combat_complete" if defeated else ("player_turn_ready" if resolved_enemy else "awaiting_enemy_turn"),
        },
        "enemy_turn": {
            "schema": "enemy_turn_skeleton_v1",
            "pending": False if (defeated or resolved_enemy) else True,
            "resolved": True if resolved_enemy else False,
            "actor_id": "" if defeated else "enemy:road_bandit",
            "reason": "combat_ended" if defeated else ("enemy_damage_applied_to_authoritative_combat_hp_in_pr1_6" if resolved_enemy else "enemy_turn_not_yet_resolved_in_pr1_foundation"),
        },
        "combat_log": combat_log,
        "progression_hooks": progression_hooks,
    }
    if defeated:
        lifecycle["combat_reward_result"] = reward
    if resolved_enemy:
        enemy_row = combat_log[1]
        lifecycle["player_combat_hp"] = {
            "schema": "player_combat_hp_v1",
            "source": "pr1_6_authoritative_player_combat_hp",
            "before": enemy_row["player_hp_before"],
            "after": enemy_row["player_hp_after"],
            "delta": enemy_row["player_hp_delta"],
            "authoritative": True,
            "survival_state_mutated": False,
        }
    return {
        "turn_index": turn,
        "raw_result": {
            "combat_lifecycle": lifecycle,
            "combat_log": lifecycle["combat_log"],
        },
    }


def _combat_start_turn() -> dict:
    return {
        "turn_index": 1,
        "raw_result": {
            "combat_result": {
                "reason": "combat_started",
                "damage_applied": 0,
                "defeated": False,
                "combat_ended": False,
            }
        },
    }


def test_pr12_extracts_lifecycle_from_matrix_turn():
    lifecycle = combat_lifecycle_from_matrix_turn(_turn(turn=2, before=4, after=3))

    assert lifecycle["schema"] == "combat_lifecycle_v1"
    assert lifecycle["initiative"]["next_actor_id"] == "enemy:road_bandit"
    assert lifecycle["enemy_turn"]["pending"] is True


def test_pr12_validates_expected_lifecycle_matrix_turns():
    failures = validate_combat_lifecycle_matrix_turns(
        [
            _turn(turn=2, before=4, after=3),
            _turn(turn=3, before=3, after=2),
            _turn(turn=4, before=2, after=1),
            _turn(turn=5, before=1, after=0, defeated=True),
        ]
    )

    assert failures == []


def test_pr14_validates_resolved_enemy_turn_lifecycle_matrix_turns():
    failures = validate_combat_lifecycle_matrix_turns(
        [
            _combat_start_turn(),
            _turn(turn=2, before=4, after=3, resolved_enemy=True),
            _turn(turn=3, before=3, after=2, resolved_enemy=True),
            _turn(turn=4, before=2, after=1, resolved_enemy=True),
            _turn(turn=5, before=1, after=0, defeated=True),
        ]
    )

    assert failures == []


def test_pr131_allows_initial_combat_started_turn_without_lifecycle():
    failures = validate_combat_lifecycle_matrix_turns(
        [
            _combat_start_turn(),
            _turn(turn=2, before=4, after=3),
            _turn(turn=3, before=3, after=2),
            _turn(turn=4, before=2, after=1),
            _turn(turn=5, before=1, after=0, defeated=True),
        ]
    )

    assert failures == []


def test_pr12_rejects_missing_lifecycle():
    failures = validate_combat_lifecycle_matrix_turns([{"turn_index": 2, "raw_result": {}}])

    assert any("missing combat_lifecycle_v1" in failure for failure in failures)


def test_pr12_rejects_combat_log_hp_delta_mismatch():
    turn = _turn(turn=2, before=4, after=3)
    turn["raw_result"]["combat_lifecycle"]["combat_log"][0]["target_hp_after"] = 4

    failures = validate_combat_lifecycle_matrix_turns([turn])

    assert any("enemy HP delta mismatch" in failure for failure in failures)


def test_pr12_rejects_non_final_without_enemy_turn_pending_or_resolved():
    turn = _turn(turn=2, before=4, after=3)
    turn["raw_result"]["combat_lifecycle"]["enemy_turn"]["pending"] = False
    turn["raw_result"]["combat_lifecycle"]["enemy_turn"]["resolved"] = False

    failures = validate_combat_lifecycle_matrix_turns([turn])

    assert any("non-final enemy_turn should be pending or resolved" in failure for failure in failures)


def test_pr14_rejects_resolved_enemy_turn_without_enemy_action_log_row():
    turn = _turn(turn=2, before=4, after=3, resolved_enemy=True)
    turn["raw_result"]["combat_lifecycle"]["combat_log"] = turn["raw_result"]["combat_lifecycle"]["combat_log"][:1]

    failures = validate_combat_lifecycle_matrix_turns([turn])

    assert any("resolved enemy turn missing enemy_action log row" in failure for failure in failures)


def test_pr15_rejects_resolved_enemy_turn_without_damage_contract():
    turn = _turn(turn=2, before=4, after=3, resolved_enemy=True)
    del turn["raw_result"]["combat_lifecycle"]["combat_log"][1]["enemy_damage_contract"]

    failures = validate_combat_lifecycle_matrix_turns([turn])

    assert any("missing enemy_damage_contract_v1" in failure for failure in failures)


def test_pr16_rejects_enemy_damage_that_does_not_mutate_combat_hp():
    turn = _turn(turn=2, before=4, after=3, resolved_enemy=True)
    turn["raw_result"]["combat_lifecycle"]["combat_log"][1]["player_state_mutated"] = False

    failures = validate_combat_lifecycle_matrix_turns([turn])

    assert any("should mutate authoritative combat HP" in failure for failure in failures)


def test_pr16_rejects_broken_player_hp_persistence_across_enemy_turns():
    turn2 = _turn(turn=2, before=4, after=3, resolved_enemy=True)
    turn3 = _turn(turn=3, before=3, after=2, resolved_enemy=True)
    turn3["raw_result"]["combat_lifecycle"]["combat_log"][1]["player_hp_before"] = 10
    turn3["raw_result"]["combat_lifecycle"]["combat_log"][1]["target_hp_before"] = 10

    failures = validate_combat_lifecycle_matrix_turns([turn2, turn3, _turn(turn=5, before=1, after=0, defeated=True)])

    assert any("player combat HP should persist across enemy turns" in failure for failure in failures)


def test_pr18_rejects_final_without_resolved_reward():
    turn = _turn(turn=5, before=1, after=0, defeated=True)
    turn["raw_result"]["combat_lifecycle"]["progression_hooks"]["resolved"] = False
    turn["raw_result"]["combat_lifecycle"].pop("combat_reward_result")

    failures = validate_combat_lifecycle_matrix_turns([turn])

    assert any("missing combat_reward_result_v1" in failure for failure in failures)
    assert any("final progression hooks should be resolved" in failure for failure in failures)


def test_pr18_rejects_final_reward_without_positive_xp():
    turn = _turn(turn=5, before=1, after=0, defeated=True)
    turn["raw_result"]["combat_lifecycle"]["combat_reward_result"]["xp_awarded"] = 0

    failures = validate_combat_lifecycle_matrix_turns([turn])

    assert any("xp_awarded should be positive" in failure for failure in failures)
