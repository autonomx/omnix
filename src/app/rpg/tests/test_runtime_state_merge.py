from app.rpg.session.runtime import _merge_stepped_simulation_state


def test_merge_stepped_simulation_state_preserves_authoritative_turn_roots():
    authoritative_state = {
        "tick": 10,
        "player_state": {
            "inventory_state": {
                "currency": {"gold": 0, "silver": 5, "copper": 0},
                "items": [],
            }
        },
        "memory_state": {
            "service_memories": [{"memory_id": "memory:prior"}],
            "npc_memories": {"npc:Bran": [{"memory_id": "memory:prior"}]},
        },
        "relationship_state": {"npc:Bran::player": {"axes": {"familiarity": 0.25}}},
        "npc_emotion_state": {"npc:Bran": {"dominant_emotion": "neutral"}},
        "service_offer_state": {"offers": {"bran_lodging_common_cot": {"stock_remaining": 2}}},
        "transaction_history": [{"transaction_id": "txn:1"}],
        "active_services": [{"service_id": "bran_lodging_common_cot"}],
        "active_interactions": [{"id": "interaction:1"}],
    }

    stepped_state = {
        "tick": 11,
        "threads": {"thread:market": {"pressure": 2}},
        "history": [{"tick": 11, "summary": ["World state advanced."]}],
        "events": [{"type": "world_event", "actor": "system"}],
    }

    merged = _merge_stepped_simulation_state(authoritative_state, stepped_state)

    assert merged["tick"] == 11
    assert merged["threads"]["thread:market"]["pressure"] == 2
    assert merged["player_state"]["inventory_state"]["currency"]["silver"] == 5
    assert merged["memory_state"]["service_memories"][0]["memory_id"] == "memory:prior"
    assert merged["relationship_state"]["npc:Bran::player"]["axes"]["familiarity"] == 0.25
    assert merged["npc_emotion_state"]["npc:Bran"]["dominant_emotion"] == "neutral"
    assert merged["service_offer_state"]["offers"]["bran_lodging_common_cot"]["stock_remaining"] == 2
    assert merged["transaction_history"][0]["transaction_id"] == "txn:1"
    assert merged["active_services"][0]["service_id"] == "bran_lodging_common_cot"
    assert merged["active_interactions"][0]["id"] == "interaction:1"