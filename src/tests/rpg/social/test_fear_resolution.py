from app.rpg.social.reputation import (
    get_global_reputation,
    get_relationship,
    set_relationship_values,
)
from app.rpg.social.resolution import resolve_intimidation


def test_intimidation_success_creates_fear_and_lowers_trust():
    simulation_state = {}
    set_relationship_values(simulation_state, "bran", {"trust": 20, "fear": 0})

    result = resolve_intimidation(
        simulation_state,
        "bran",
        threat="I will expose your secret.",
        severity=90,
        profile={"npc_id": "bran", "bravery": 35, "stubbornness": 30},
    )

    relationship = get_relationship(simulation_state, "bran")
    assert result["ok"] is True
    assert result["stance"] == "fearful"
    assert relationship["fear"] > 0
    assert relationship["trust"] < 20


def test_failed_intimidation_escalates_hostility():
    simulation_state = {}
    result = resolve_intimidation(
        simulation_state,
        "bran",
        threat="weak threat",
        severity=10,
        profile={"npc_id": "bran", "bravery": 90, "stubbornness": 90},
    )

    relationship = get_relationship(simulation_state, "bran")
    assert result["ok"] is False
    assert result["escalation"] is True
    assert result["stance"] == "hostile"
    assert relationship["hostility"] > 0


def test_public_intimidation_lowers_global_reputation_and_affects_witnesses():
    simulation_state = {}
    result = resolve_intimidation(
        simulation_state,
        "bran",
        threat="public threat",
        severity=90,
        profile={"npc_id": "bran", "bravery": 35, "stubbornness": 30},
        witnesses=["mira"],
    )

    assert result["ok"] is True
    assert result["public_reputation_delta"] < 0
    assert get_global_reputation(simulation_state, "player") < 0
    assert get_relationship(simulation_state, "mira")["trust"] < 0