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
