from app.rpg.lore.conditions import evaluate_lore_condition
from app.rpg.lore.state import reveal_lore_to_player, upsert_lore_entry


def test_lore_revealed_condition():
    simulation_state = {}
    upsert_lore_entry(simulation_state, {"lore_id": "lore:red_sashes", "title": "The Red Sashes"})
    reveal_lore_to_player(simulation_state, "lore:red_sashes")

    result = evaluate_lore_condition(
        simulation_state,
        {"type": "lore_revealed_to_player", "lore_id": "lore:red_sashes"},
    )

    assert result["ok"] is True


def test_lore_known_by_condition():
    simulation_state = {}
    upsert_lore_entry(
        simulation_state,
        {
            "lore_id": "lore:red_sashes",
            "title": "The Red Sashes",
            "known_by": ["bran"],
        },
    )

    result = evaluate_lore_condition(
        simulation_state,
        {"type": "lore_known_by", "lore_id": "lore:red_sashes", "entity_id": "bran"},
    )

    assert result["ok"] is True


def test_lore_truth_status_condition():
    simulation_state = {}
    upsert_lore_entry(simulation_state, {"lore_id": "lore:rumor", "title": "Rumor", "truth_status": "rumor"})

    result = evaluate_lore_condition(
        simulation_state,
        {"type": "lore_truth_status", "lore_id": "lore:rumor", "truth_status": "rumor"},
    )

    assert result["ok"] is True