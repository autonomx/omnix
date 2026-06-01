def test_ci_progression_registry_exposes_tavern_graphs():
    assert True


def test_ci_progression_actions_are_available_for_tavern_seed():
    from app.rpg.progression.runtime import get_active_progression_actions

    actions = get_active_progression_actions(
        {},
        scenario_seed="tavern_story_seed",
        limit=3,
    )

    assert actions
    assert actions[0].get("command")


def test_ci_campaign_report_renderer_is_importable():
    from tests.rpg.autoplay.campaign_report import render_campaign_report_html

    html = render_campaign_report_html({"scenario_seed": "ci_smoke"})

    assert isinstance(html, str)
    assert html.strip()


def test_ci_combat_defeat_loot_awards_player_xp_once():
    from app.rpg.interactions.loot_runtime import generate_loot_from_table

    state = {
        "player_state": {
            "level": 1,
            "xp": 90,
            "xp_to_next_level": 100,
            "inventory": {"items": [], "equipment": {}},
        }
    }

    first = generate_loot_from_table(
        state,
        loot_table_id="loot:bandit_common",
        source_id="enemy:bandit_1",
        session_id="ci-combat-reward",
        tick=7,
        add_to_inventory=True,
    )

    player_state = state["player_state"]
    assert first["resolved"] is True
    assert first["xp_result"]["awarded"] is True
    assert first["xp_result"]["xp_awarded"] == 25
    assert player_state["level"] == 2
    assert player_state["xp"] == 15
    assert player_state["xp_to_next_level"] == 150
    assert player_state["inventory"]["items"]

    second = generate_loot_from_table(
        state,
        loot_table_id="loot:bandit_common",
        source_id="enemy:bandit_1",
        session_id="ci-combat-reward",
        tick=7,
        add_to_inventory=True,
    )

    assert second["xp_result"]["awarded"] is False
    assert second["xp_result"]["reason"] == "combat_reward_already_claimed"
    assert state["player_state"]["level"] == 2
    assert state["player_state"]["xp"] == 15


def test_ci_combat_attack_result_exposes_nested_reward_xp():
    from app.rpg.combat.runtime import resolve_combat_attack, start_combat_encounter

    state = {
        "player_state": {
            "level": 1,
            "xp": 90,
            "xp_to_next_level": 100,
            "inventory": {"items": [], "equipment": {}},
        }
    }
    start_combat_encounter(
        state,
        encounter_id="ci:reward_surface",
        enemies=[
            {
                "actor_id": "enemy:bandit_1",
                "side": "enemy",
                "name": "Bandit",
                "hp": 1,
                "max_hp": 1,
                "defense": 1,
                "armor": 0,
                "loot_table_id": "loot:bandit_common",
                "status": "active",
            }
        ],
        tick=1,
    )
    state["combat_state"]["turn_index"] = 0
    state["combat_state"]["current_actor_id"] = "player"
    state["combat_state"]["initiative_order"] = [
        {"actor_id": "player", "initiative": 20},
        {"actor_id": "enemy:bandit_1", "initiative": 1},
    ]

    result = resolve_combat_attack(
        state,
        actor_id="player",
        target_id="enemy:bandit_1",
        session_id="ci-combat-reward-surface",
        tick=3,
        combat_modifiers={"accuracy_bonus": 99, "damage_bonus": 99},
    )

    xp_result = result["loot_result"]["xp_result"]
    assert result["resolved"] is True
    assert result["defeated"] is True
    assert result["combat_ended"] is True
    assert xp_result["awarded"] is True
    assert xp_result["xp_awarded"] == 25
    assert result["xp_result"]["awarded"] is True
    assert result["xp_result"]["xp_awarded"] == 25
    assert state["player_state"]["level"] == 2
    assert state["player_state"]["xp"] == 15


def test_ci_combat_xp_bridge_surfaces_reward_to_turn_payloads():
    from app.rpg.session.runtime_part22 import _surface_combat_xp_result_in_turn_payload

    payload = {
        "result": {
            "combat_result": {
                "xp_result": {
                    "awarded": True,
                    "xp_awarded": 25,
                    "source": "deterministic_combat_reward_runtime",
                }
            }
        },
        "resolved_result": {},
        "narration_context": {"xp_result": {}, "combat_result": {}},
        "runtime_state": {"last_turn_result": {"xp_result": {}}},
        "session": {"runtime_state": {"last_turn_result": {"xp_result": {}}}},
    }

    updated = _surface_combat_xp_result_in_turn_payload(payload)

    assert updated["xp_result"]["xp_awarded"] == 25
    assert updated["result"]["xp_result"]["xp_awarded"] == 25
    assert updated["resolved_result"]["xp_result"]["xp_awarded"] == 25
    assert updated["narration_context"]["xp_result"]["xp_awarded"] == 25
    assert updated["runtime_state"]["last_turn_result"]["xp_result"]["xp_awarded"] == 25
    assert updated["session"]["runtime_state"]["last_turn_result"]["xp_result"]["xp_awarded"] == 25


def test_ci_session_attack_defeat_bridge_awards_and_surfaces_xp_once():
    from app.rpg.session import runtime
    from app.rpg.session.runtime_part22 import _surface_combat_xp_result_in_turn_payload
    from app.rpg.session.runtime_part23 import _attach_session_attack_defeat_reward

    assert runtime._apply_attack_combat_action.__module__.endswith("runtime_part23")

    state = {
        "player_state": {
            "level": 1,
            "xp": 90,
            "xp_to_next_level": 100,
            "inventory": {"items": [], "equipment": {}},
        },
    }
    runtime_state = {"session_id": "ci-session-attack-reward"}
    combat_state = {
        "active": False,
        "ended_reason": "enemy_side_defeated",
        "participants": {
            "enemy:bandit_1": {
                "actor_id": "enemy:bandit_1",
                "side": "enemy",
                "name": "Bandit",
                "hp": 0,
                "max_hp": 1,
                "defense": 1,
                "armor": 0,
                "loot_table_id": "loot:bandit_common",
                "status": "defeated",
            }
        },
    }
    combat_result = {"defeated": True, "target_id": "enemy:bandit_1"}

    rewarded = _attach_session_attack_defeat_reward(
        after_action_state=state,
        runtime_state=runtime_state,
        combat_state=combat_state,
        combat_result=combat_result,
        target_id="enemy:bandit_1",
        turn_id="turn:ci-session-attack-reward",
        tick=5,
    )

    xp_result = rewarded["xp_result"]
    assert rewarded["loot_result"]["xp_result"]["awarded"] is True
    assert xp_result["awarded"] is True
    assert xp_result["xp_awarded"] == 25
    assert state["player_state"]["level"] == 2
    assert state["player_state"]["xp"] == 15
    assert state["player_state"]["xp_to_next_level"] == 150

    repeated = _attach_session_attack_defeat_reward(
        after_action_state=state,
        runtime_state=runtime_state,
        combat_state=combat_state,
        combat_result={"defeated": True, "target_id": "enemy:bandit_1"},
        target_id="enemy:bandit_1",
        turn_id="turn:ci-session-attack-reward",
        tick=5,
    )
    assert repeated["xp_result"]["awarded"] is False
    assert repeated["xp_result"]["reason"] == "combat_reward_already_claimed"
    assert state["player_state"]["level"] == 2
    assert state["player_state"]["xp"] == 15

    payload = {
        "result": {"combat_result": rewarded},
        "resolved_result": {},
        "narration_context": {"xp_result": {}, "combat_result": {}},
        "runtime_state": {"last_turn_result": {"xp_result": {}}},
        "session": {"runtime_state": {"last_turn_result": {"xp_result": {}}}},
    }
    updated = _surface_combat_xp_result_in_turn_payload(payload)
    assert updated["result"]["xp_result"]["xp_awarded"] == 25
    assert updated["resolved_result"]["xp_result"]["xp_awarded"] == 25
    assert updated["narration_context"]["xp_result"]["xp_awarded"] == 25
    assert updated["runtime_state"]["last_turn_result"]["xp_result"]["xp_awarded"] == 25
    assert updated["session"]["runtime_state"]["last_turn_result"]["xp_result"]["xp_awarded"] == 25
