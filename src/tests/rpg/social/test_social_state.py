from app.rpg.social.reputation import get_relationship, set_relationship_values
from app.rpg.social.state import (
    ensure_social_state,
    normalize_social_profile,
    normalize_social_state,
)


def test_social_state_normalizes_relationships():
    simulation_state = {
        "social_state": {
            "relationships": {
                "bran": {
                    "trust": 999,
                    "fear": -999,
                    "hostility": 12,
                }
            }
        }
    }

    state = ensure_social_state(simulation_state)

    assert state["relationships"]["bran"]["trust"] == 100
    assert state["relationships"]["bran"]["fear"] == -100
    assert state["relationships"]["bran"]["hostility"] == 12


def test_set_relationship_values_clamps():
    simulation_state = {}
    relationship = set_relationship_values(
        simulation_state,
        "bran",
        {"trust": 150, "fear": -150, "last_stance": "cooperative"},
    )

    assert relationship["trust"] == 100
    assert relationship["fear"] == -100
    assert get_relationship(simulation_state, "bran")["last_stance"] == "cooperative"


def test_normalize_social_profile_defaults():
    profile = normalize_social_profile({}, npc_id="bran")

    assert profile["npc_id"] == "bran"
    assert profile["bravery"] == 50
    assert profile["stubbornness"] == 40


def test_normalize_social_state_preserves_manual_results():
    state = normalize_social_state(
        {
            "manual_results": {
                "discount_room": {
                    "ok": True,
                    "kind": "persuasion",
                    "stance": "cooperative",
                }
            }
        }
    )

    assert state["manual_results"]["discount_room"]["ok"] is True
    assert state["manual_results"]["discount_room"]["stance"] == "cooperative"
