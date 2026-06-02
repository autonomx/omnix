def _completed_quest_state():
    from app.rpg.quests.givers import accept_quest_offer
    from app.rpg.quests.objectives import complete_objective_lifecycle

    state = {"player_state": {"inventory_state": {"items": [], "currency": {"silver": 2}}}}
    accept_quest_offer(state, giver_id="npc:bran", quest_id="quest:clear_the_road", turn_index=2)
    complete_objective_lifecycle(
        state,
        quest_id="quest:clear_the_road",
        objective_id="objective:defeat_bandit",
        turn_index=8,
    )
    return state


def test_ci_phase3_reward_payload_is_source_backed_and_stable():
    from app.rpg.quests.rewards import build_reward_payload

    state = _completed_quest_state()
    rewards = [{"type": "currency", "currency": {"silver": 12}}]
    first = build_reward_payload(state, "quest:clear_the_road", rewards)
    second = build_reward_payload(state, "quest:clear_the_road", rewards)

    assert first["ok"] is True
    assert first["reason"] == "reward_payload_built"
    assert first["reward_id"] == second["reward_id"]
    assert first["source"] == "deterministic_quest_reward_rules"
    assert first["rewards"][0]["source"] == "deterministic_quest_reward_rules"


def test_ci_phase3_completed_quest_rewards_apply_currency_and_relationship_once():
    from app.rpg.economy.currency import get_player_currency
    from app.rpg.quests.rewards import claim_quest_rewards

    state = _completed_quest_state()
    result = claim_quest_rewards(state, quest_id="quest:clear_the_road", turn_index=9)
    second = claim_quest_rewards(state, quest_id="quest:clear_the_road", turn_index=10)

    effects = {effect["type"]: effect for effect in result["effects"]}
    assert result["ok"] is True
    assert result["reason"] == "rewards_claimed"
    assert result["source"] == "deterministic_quest_reward_rules"
    assert effects["currency"]["currency"] == {"gold": 0, "silver": 12, "copper": 0}
    assert get_player_currency(state) == {"gold": 1, "silver": 4, "copper": 0}
    assert effects["relationship"]["npc_id"] == "npc:bran"
    assert state["player_state"]["relationships"]["npc:bran"]["trust"] == 5
    assert state["quest_state"]["quests"]["quest:clear_the_road"]["reward_claimed"] is True
    assert state["reward_state"]["log"][-1]["source"] == "deterministic_quest_reward_rules"
    assert second["ok"] is True
    assert second["reason"] == "already_claimed"
    assert second["effects"] == []
    assert get_player_currency(state) == {"gold": 1, "silver": 4, "copper": 0}


def test_ci_phase3_item_rewards_add_inventory_items():
    from app.rpg.quests.rewards import claim_quest_rewards

    state = _completed_quest_state()
    quest = state["quest_state"]["quests"]["quest:clear_the_road"]
    quest["rewards"] = [{"type": "item", "item_id": "healing_potion", "qty": 2}]

    result = claim_quest_rewards(state, quest_id="quest:clear_the_road", turn_index=9)
    items = {item["item_id"]: item["qty"] for item in state["player_state"]["inventory_state"]["items"]}

    assert result["ok"] is True
    assert result["effects"][0]["type"] == "item"
    assert result["effects"][0]["source"] == "deterministic_quest_reward_rules"
    assert items["healing_potion"] == 2


def test_ci_phase3_rewards_reject_incomplete_or_missing_quest_without_mutation():
    from copy import deepcopy

    from app.rpg.quests.givers import accept_quest_offer
    from app.rpg.quests.rewards import claim_quest_rewards

    missing_state = {}
    missing = claim_quest_rewards(missing_state, quest_id="quest:missing", turn_index=1)

    state = {"player_state": {"inventory_state": {"currency": {"silver": 2}}}}
    accept_quest_offer(state, giver_id="npc:bran", quest_id="quest:clear_the_road", turn_index=2)
    before = deepcopy(state)
    incomplete = claim_quest_rewards(state, quest_id="quest:clear_the_road", turn_index=3)

    assert missing["ok"] is False
    assert missing["reason"] == "quest_missing"
    assert missing_state == {}
    assert incomplete["ok"] is False
    assert incomplete["reason"] == "quest_not_completed"
    assert incomplete["source"] == "deterministic_quest_reward_rules"
    assert state == before


def test_ci_phase3_mark_reward_claimed_uses_reward_rules_api():
    from app.rpg.quests.rewards import mark_reward_claimed

    state = _completed_quest_state()
    result = mark_reward_claimed(state, "quest:clear_the_road")

    assert result["ok"] is True
    assert result["reason"] == "rewards_claimed"
    assert result["source"] == "deterministic_quest_reward_rules"


def test_ci_phase3_reward_helpers_are_exported():
    from app.rpg import quests

    assert quests.build_reward_payload
    assert quests.claim_quest_rewards
    assert quests.mark_reward_claimed
