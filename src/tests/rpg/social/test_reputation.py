from app.rpg.social.reputation import (
    apply_social_deltas,
    get_global_reputation,
    get_relationship,
    set_global_reputation,
)


def test_apply_social_deltas_updates_relationship():
    simulation_state = {}
    apply_social_deltas(
        simulation_state,
        "bran",
        {"trust": 10, "fear": 5, "hostility": -2, "last_stance": "cautious"},
    )

    relationship = get_relationship(simulation_state, "bran")
    assert relationship["trust"] == 10
    assert relationship["fear"] == 5
    assert relationship["hostility"] == -2
    assert relationship["last_stance"] == "cautious"


def test_global_reputation_clamps():
    simulation_state = {}
    assert set_global_reputation(simulation_state, "player", 500) == 100
    assert get_global_reputation(simulation_state, "player") == 100