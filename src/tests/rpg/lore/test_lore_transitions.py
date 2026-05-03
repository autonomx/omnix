from app.rpg.lore.state import get_lore_entry, is_lore_available_to_player
from app.rpg.lore.transitions import apply_lore_transition


def test_lore_transition_upsert_and_reveal():
    simulation_state = {}
    apply_lore_transition(
        simulation_state,
        {
            "action": "upsert",
            "lore_id": "lore:red_sashes",
            "title": "The Red Sashes",
            "truth_status": "true",
        },
    )
    apply_lore_transition(
        simulation_state,
        {"action": "reveal_to_player", "lore_id": "lore:red_sashes"},
    )

    assert get_lore_entry(simulation_state, "lore:red_sashes")["truth_status"] == "true"
    assert is_lore_available_to_player(simulation_state, "lore:red_sashes") is True


def test_lore_transition_add_known_by():
    simulation_state = {}
    apply_lore_transition(simulation_state, {"action": "upsert", "lore_id": "lore:secret", "title": "Secret"})
    result = apply_lore_transition(
        simulation_state,
        {"action": "add_known_by", "lore_id": "lore:secret", "entity_id": "bran"},
    )

    assert result["ok"] is True
    assert "bran" in get_lore_entry(simulation_state, "lore:secret")["known_by"]