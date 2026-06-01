def test_ci_progression_registry_exposes_tavern_graphs():
    assert True


def test_ci_progression_actions_are_available_for_tavern_seed():
    from app.rpg.progression.runtime import get_active_progression_actions

    actions = get_active_progression_actions({}, scenario_seed="tavern_story_seed", limit=3)
    assert actions
    assert actions[0].get("command")


def test_ci_campaign_report_renderer_is_importable():
    from tests.rpg.autoplay.campaign_report import render_campaign_report_html

    html = render_campaign_report_html({"scenario_seed": "ci_smoke"})
    assert isinstance(html, str)
    assert html.strip()


def test_ci_combat_defeat_loot_awards_player_xp_once():
    from app.rpg.interactions.loot_runtime import generate_loot_from_table

    state = {"player_state": {"level": 1, "xp": 90, "xp_to_next_level": 100, "inventory": {"items": [], "equipment": {}}}}
    first = generate_loot_from_table(state, loot_table_id="loot:bandit_common", source_id="enemy:bandit_1", session_id="ci-combat-reward", tick=7, add_to_inventory=True)
    assert first["resolved"] is True
    assert first["xp_result"]["awarded"] is True
    assert first["xp_result"]["xp_awarded"] == 25
    assert state["player_state"]["level"] == 2
    assert state["player_state"]["xp"] == 15
    assert state["player_state"]["xp_to_next_level"] == 150
    assert state["player_state"]["inventory"]["items"]

    second = generate_loot_from_table(state, loot_table_id="loot:bandit_common", source_id="enemy:bandit_1", session_id="ci-combat-reward", tick=7, add_to_inventory=True)
    assert second["xp_result"]["awarded"] is False
    assert second["xp_result"]["reason"] == "combat_reward_already_claimed"
    assert state["player_state"]["level"] == 2
    assert state["player_state"]["xp"] == 15


def test_ci_combat_attack_result_exposes_nested_reward_xp():
    from app.rpg.combat.runtime import resolve_combat_attack, start_combat_encounter

    state = {"player_state": {"level": 1, "xp": 90, "xp_to_next_level": 100, "inventory": {"items": [], "equipment": {}}}}
    start_combat_encounter(state, encounter_id="ci:reward_surface", enemies=[{"actor_id": "enemy:bandit_1", "side": "enemy", "name": "Bandit", "hp": 1, "max_hp": 1, "defense": 1, "armor": 0, "loot_table_id": "loot:bandit_common", "status": "active"}], tick=1)
    state["combat_state"]["turn_index"] = 0
    state["combat_state"]["current_actor_id"] = "player"
    state["combat_state"]["initiative_order"] = [{"actor_id": "player", "initiative": 20}, {"actor_id": "enemy:bandit_1", "initiative": 1}]
    result = resolve_combat_attack(state, actor_id="player", target_id="enemy:bandit_1", session_id="ci-combat-reward-surface", tick=3, combat_modifiers={"accuracy_bonus": 99, "damage_bonus": 99})
    assert result["resolved"] is True
    assert result["defeated"] is True
    assert result["combat_ended"] is True
    assert result["loot_result"]["xp_result"]["xp_awarded"] == 25
    assert result["xp_result"]["xp_awarded"] == 25
    assert state["player_state"]["level"] == 2
    assert state["player_state"]["xp"] == 15


def test_ci_combat_xp_bridge_surfaces_reward_to_turn_payloads():
    from app.rpg.session.runtime_part22 import _surface_combat_xp_result_in_turn_payload

    payload = {"result": {"combat_result": {"xp_result": {"awarded": True, "xp_awarded": 25, "source": "deterministic_combat_reward_runtime"}}}, "resolved_result": {}, "narration_context": {"xp_result": {}, "combat_result": {}}, "runtime_state": {"last_turn_result": {"xp_result": {}}}, "session": {"runtime_state": {"last_turn_result": {"xp_result": {}}}}}
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
    state = {"player_state": {"level": 1, "xp": 90, "xp_to_next_level": 100, "inventory": {"items": [], "equipment": {}}}}
    combat_state = {"active": False, "ended_reason": "enemy_side_defeated", "participants": {"enemy:bandit_1": {"actor_id": "enemy:bandit_1", "side": "enemy", "name": "Bandit", "hp": 0, "max_hp": 1, "defense": 1, "armor": 0, "loot_table_id": "loot:bandit_common", "status": "defeated"}}}
    rewarded = _attach_session_attack_defeat_reward(after_action_state=state, runtime_state={"session_id": "ci-session-attack-reward"}, combat_state=combat_state, combat_result={"defeated": True, "target_id": "enemy:bandit_1"}, target_id="enemy:bandit_1", turn_id="turn:ci-session-attack-reward", tick=5)
    assert rewarded["xp_result"]["awarded"] is True
    assert rewarded["xp_result"]["xp_awarded"] == 25
    assert state["player_state"]["level"] == 2
    assert state["player_state"]["xp"] == 15
    repeated = _attach_session_attack_defeat_reward(after_action_state=state, runtime_state={"session_id": "ci-session-attack-reward"}, combat_state=combat_state, combat_result={"defeated": True, "target_id": "enemy:bandit_1"}, target_id="enemy:bandit_1", turn_id="turn:ci-session-attack-reward", tick=5)
    assert repeated["xp_result"]["awarded"] is False
    assert repeated["xp_result"]["reason"] == "combat_reward_already_claimed"
    updated = _surface_combat_xp_result_in_turn_payload({"result": {"combat_result": rewarded}, "resolved_result": {}, "narration_context": {"xp_result": {}, "combat_result": {}}, "runtime_state": {"last_turn_result": {"xp_result": {}}}, "session": {"runtime_state": {"last_turn_result": {"xp_result": {}}}}})
    assert updated["result"]["xp_result"]["xp_awarded"] == 25
    assert updated["resolved_result"]["xp_result"]["xp_awarded"] == 25


def test_ci_campaign_report_displays_combat_xp_rewards():
    from tests.rpg.autoplay.campaign_report import render_campaign_report_html

    html = render_campaign_report_html({"scenario_seed": "ci_combat_xp_report", "turns": [{"turn": 3, "result": {"action_type": "attack", "combat_result": {"target_id": "enemy:bandit_1", "reason": "combat_defeat_resolved", "xp_result": {"awarded": True, "xp_awarded": 25, "source": "deterministic_combat_reward_runtime"}}}, "resolved_result": {}, "narration_context": {}}]})
    assert "Combat XP Rewards" in html
    assert "Total deterministic combat XP shown in turn payloads" in html
    assert "<strong>25</strong>" in html
    assert "enemy:bandit_1" in html
    assert "combat_defeat_resolved" in html


def test_ci_combat_reward_narrative_contract_limits_reward_claims():
    from app.rpg.session import runtime
    from app.rpg.session.runtime_part24 import _apply_combat_reward_narrative_contract

    assert runtime._apply_turn_authoritative.__module__.endswith(("runtime_part24", "runtime_part25"))
    payload = {"result": {"combat_result": {"xp_result": {"awarded": True, "xp_awarded": 25, "source": "deterministic_combat_reward_runtime"}, "loot_result": {"items": [{"item_id": "item:rusty_dagger", "quantity": 1}], "currency": {"silver": 2}}}}, "resolved_result": {}, "narration_context": {"forbidden_narration": ["existing guardrail"]}}
    updated = _apply_combat_reward_narrative_contract(payload)
    contract = updated["combat_reward_narrative_contract"]
    assert contract["source"] == "deterministic_combat_reward_contract"
    assert contract["reward_lines"] == ["XP +25", "Loot: 1 x item:rusty_dagger", "Loot: 2 silver"]
    assert updated["narration_context"]["reward_lines"] == contract["reward_lines"]
    assert "XP +25" in updated["narration_context"]["allowed_reward_claims"]
    assert "existing guardrail" in updated["narration_context"]["forbidden_narration"]
    assert any("Do not invent XP" in claim for claim in updated["narration_context"]["forbidden_narration"])
    assert any("Do not change awarded XP" in claim for claim in updated["narration_context"]["forbidden_narration"])
    assert updated["result"]["combat_reward_narrative_contract"] == contract
    assert updated["resolved_result"]["combat_reward_narrative_contract"] == contract


def test_ci_combat_end_state_syncs_matching_quest_objective():
    from app.rpg.session import runtime
    from app.rpg.session.runtime_part25 import _sync_combat_end_state_to_quests

    assert runtime._apply_turn_authoritative.__module__.endswith("runtime_part25")
    payload = {"tick": 8, "simulation_state": {"quest_state": {"active_quests": [{"quest_id": "quest:clear_the_road", "status": "active", "objectives": [{"objective_id": "objective:defeat_bandit", "type": "defeat", "target_id": "enemy:bandit_1", "status": "active", "current": 0, "required": 1}]}]}}, "result": {"combat_result": {"combat_ended": True, "ended_reason": "enemy_side_defeated", "target_id": "enemy:bandit_1", "tick": 8}}, "resolved_result": {}, "narration_context": {}}
    updated = _sync_combat_end_state_to_quests(payload)
    quest = updated["simulation_state"]["quest_state"]["active_quests"][0]
    objective = quest["objectives"][0]
    sync_result = updated["combat_quest_sync_result"]
    assert objective["status"] == "completed"
    assert objective["current"] == 1
    assert objective["completed_at_tick"] == 8
    assert quest["status"] == "completed"
    assert quest["completed_at_tick"] == 8
    assert sync_result["source"] == "deterministic_combat_quest_sync"
    assert sync_result["updated_objectives"][0]["objective_id"] == "objective:defeat_bandit"
    assert sync_result["completed_quests"] == ["quest:clear_the_road"]
    assert updated["result"]["combat_quest_sync_result"] == sync_result
    assert updated["resolved_result"]["combat_quest_sync_result"] == sync_result
    assert updated["narration_context"]["combat_quest_sync_result"] == sync_result
    assert "Quest objective completed: objective:defeat_bandit" in updated["narration_context"]["quest_progress_lines"]


def test_ci_campaign_report_displays_combat_quest_sync():
    from tests.rpg.autoplay.campaign_report import render_campaign_report_html

    html = render_campaign_report_html({"scenario_seed": "ci_combat_quest_sync_report", "turns": [{"turn": 8, "combat_quest_sync_result": {"source": "deterministic_combat_quest_sync", "reason": "combat_end_state_enemy_side_defeated", "target_ids": ["enemy:bandit_1"], "updated_objectives": [{"quest_id": "quest:clear_the_road", "objective_id": "objective:defeat_bandit", "target_ids": ["enemy:bandit_1"], "status": "completed"}], "completed_quests": ["quest:clear_the_road"]}}]})
    assert "Combat Quest Sync" in html
    assert "Combat-synced objectives" in html
    assert "completed quests" in html
    assert "quest:clear_the_road" in html
    assert "objective:defeat_bandit" in html
    assert "enemy:bandit_1" in html
    assert "combat_end_state_enemy_side_defeated" in html
