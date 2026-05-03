from app.rpg.lore.state import (
    add_lore_known_by,
    get_lore_entry,
    is_lore_available_to_player,
    is_lore_known_by,
    reveal_lore_to_player,
    set_lore_truth_status,
    upsert_lore_entry,
)


def test_lore_entry_upsert_and_reveal():
    simulation_state = {}
    upsert_lore_entry(
        simulation_state,
        {
            "lore_id": "lore:red_sashes",
            "title": "The Red Sashes",
            "kind": "faction",
            "truth_status": "true",
            "known_by": ["bran"],
            "tags": ["bandits"],
        },
    )

    assert get_lore_entry(simulation_state, "lore:red_sashes")["title"] == "The Red Sashes"
    assert is_lore_available_to_player(simulation_state, "lore:red_sashes") is False

    reveal_lore_to_player(simulation_state, "lore:red_sashes")
    assert is_lore_available_to_player(simulation_state, "lore:red_sashes") is True


def test_lore_known_by_and_truth_status():
    simulation_state = {}
    upsert_lore_entry(simulation_state, {"lore_id": "lore:secret", "title": "Secret", "truth_status": "secret"})
    add_lore_known_by(simulation_state, "lore:secret", "bran")
    set_lore_truth_status(simulation_state, "lore:secret", "rumor")

    entry = get_lore_entry(simulation_state, "lore:secret")
    assert is_lore_known_by(simulation_state, "lore:secret", "bran") is True
    assert entry["truth_status"] == "rumor"


def test_rumor_not_promoted_to_truth_by_reveal():
    simulation_state = {}
    upsert_lore_entry(simulation_state, {"lore_id": "lore:rumor", "title": "Rumor", "truth_status": "rumor"})
    reveal_lore_to_player(simulation_state, "lore:rumor")

    assert get_lore_entry(simulation_state, "lore:rumor")["truth_status"] == "rumor"