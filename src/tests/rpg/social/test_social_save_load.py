import json

from app.rpg.social.leverage import add_social_leverage
from app.rpg.social.reputation import set_global_reputation, set_relationship_values
from app.rpg.social.state import normalize_social_state


def test_social_state_json_roundtrip():
    simulation_state = {}
    set_relationship_values(simulation_state, "bran", {"trust": 25, "fear": 10})
    set_global_reputation(simulation_state, "player", 5)
    add_social_leverage(
        simulation_state,
        {
            "leverage_id": "lev:bran_debt",
            "npc_id": "bran",
            "kind": "debt",
            "summary": "Bran owes a favor.",
            "strength": 20,
            "valid": True,
        },
    )

    encoded = json.dumps(simulation_state["social_state"], sort_keys=True)
    decoded = json.loads(encoded)
    normalized = normalize_social_state(decoded)

    assert normalized["relationships"]["bran"]["trust"] == 25
    assert normalized["relationships"]["bran"]["fear"] == 10
    assert normalized["global_reputation"]["player"] == 5
    assert normalized["relationships"]["bran"]["leverage"][0]["leverage_id"] == "lev:bran_debt"