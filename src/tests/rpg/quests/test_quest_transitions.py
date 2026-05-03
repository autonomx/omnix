from app.rpg.quests.state import get_quest, start_quest
from app.rpg.quests.transitions import apply_quest_transition


def test_quest_start_transition():
    simulation_state = {}
    result = apply_quest_transition(
        simulation_state,
        {
            "action": "start",
            "quest_id": "quest:rat_cellar",
            "title": "Rats in the Cellar",
            "stage": "started",
        },
        turn_index=1,
    )

    assert result["ok"] is True
    assert get_quest(simulation_state, "quest:rat_cellar")["stage"] == "started"


def test_quest_transition_conditions_block_stage_change():
    simulation_state = {"manual_inventory_items": []}
    start_quest(simulation_state, "quest:rat_cellar", stage="started")
    result = apply_quest_transition(
        simulation_state,
        {
            "action": "set_stage",
            "quest_id": "quest:rat_cellar",
            "stage": "cellar_unlocked",
            "conditions": [{"type": "has_item", "item_id": "cellar_key"}],
        },
    )

    assert result["ok"] is False
    assert result["reason"] == "conditions_failed"
    assert get_quest(simulation_state, "quest:rat_cellar")["stage"] == "started"


def test_quest_complete_transition_sets_reward_payload_once():
    simulation_state = {}
    start_quest(simulation_state, "quest:rat_cellar", stage="return_to_bran")
    first = apply_quest_transition(
        simulation_state,
        {
            "action": "complete_quest",
            "quest_id": "quest:rat_cellar",
            "rewards": [{"type": "gold", "amount": 10}],
        },
        turn_index=5,
    )
    second = apply_quest_transition(
        simulation_state,
        {
            "action": "complete_quest",
            "quest_id": "quest:rat_cellar",
            "rewards": [{"type": "gold", "amount": 10}],
        },
        turn_index=6,
    )

    quest = get_quest(simulation_state, "quest:rat_cellar")
    assert first["ok"] is True
    assert second["ok"] is True
    assert len(quest["rewards"]) == 1
    assert quest["reward_claimed"] is False