from app.rpg.social.leverage import add_social_leverage
from app.rpg.social.reputation import get_relationship, set_relationship_values
from app.rpg.social.resolution import resolve_persuasion


def test_persuasion_success_high_trust():
    simulation_state = {}
    set_relationship_values(
        simulation_state,
        "bran",
        {"trust": 50, "reputation": 20, "hostility": 0},
    )

    result = resolve_persuasion(
        simulation_state,
        "bran",
        request="discounted room",
        difficulty=40,
        approach="polite",
    )

    assert result["ok"] is True
    assert result["stance"] in {"cooperative", "cautious"}
    assert get_relationship(simulation_state, "bran")["trust"] >= 50


def test_persuasion_fails_low_trust_high_difficulty():
    simulation_state = {}
    set_relationship_values(
        simulation_state,
        "bran",
        {"trust": -30, "hostility": 30},
    )

    result = resolve_persuasion(
        simulation_state,
        "bran",
        request="free room",
        difficulty=80,
        approach="polite",
    )

    assert result["ok"] is False
    assert result["stance"] in {"resistant", "dismissive", "hostile"}


def test_valid_leverage_can_help_persuasion():
    simulation_state = {}
    set_relationship_values(simulation_state, "bran", {"trust": 0, "hostility": 0})
    add_social_leverage(
        simulation_state,
        {
            "leverage_id": "lev:bran_debt",
            "npc_id": "bran",
            "kind": "debt",
            "summary": "Bran owes the player a favor.",
            "strength": 35,
            "valid": True,
            "tags": ["favor", "room"],
        },
    )

    result = resolve_persuasion(
        simulation_state,
        "bran",
        request="discounted room",
        difficulty=65,
        approach="logical",
        leverage_id="lev:bran_debt",
    )

    assert result["ok"] is True
    assert result["leverage_result"]["ok"] is True