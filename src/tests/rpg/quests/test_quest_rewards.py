from app.rpg.quests.rewards import build_reward_payload, mark_reward_claimed
from app.rpg.quests.state import start_quest


def test_reward_payload_not_auto_granted():
    simulation_state = {}
    start_quest(simulation_state, "quest:rat_cellar")

    reward = build_reward_payload(
        simulation_state,
        "quest:rat_cellar",
        [{"type": "gold", "amount": 10}],
    )

    assert reward["ok"] is True
    assert reward["auto_granted"] is False
    assert reward["already_claimed"] is False


def test_mark_reward_claimed_is_idempotent():
    simulation_state = {}
    start_quest(simulation_state, "quest:rat_cellar")
    reward = build_reward_payload(
        simulation_state,
        "quest:rat_cellar",
        [{"type": "gold", "amount": 10}],
    )

    first = mark_reward_claimed(
        simulation_state,
        "quest:rat_cellar",
        reward["reward_id"],
    )
    second = mark_reward_claimed(
        simulation_state,
        "quest:rat_cellar",
        reward["reward_id"],
    )

    assert first["ok"] is True
    assert first["reason"] == "claimed"
    assert second["ok"] is True
    assert second["reason"] == "already_claimed"