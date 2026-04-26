import os
import sys

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from tests.rpg import manual_llm_transcript as transcript


def test_sanitize_manual_simulation_state_clears_accumulated_roots():
    state = {
        "transaction_history": [{"transaction_id": "old"}],
        "active_services": [{"service_id": "old"}],
        "memory_rumors": [{"rumor_id": "old"}],
        "relationship_state": {"npc:Bran::player": {"axes": {"trust": 99}}},
        "npc_emotion_state": {"npc:Bran": {"dominant_emotion": "angry"}},
        "service_offer_state": {"offers": {"elara_torch": {"stock_remaining": 0}}},
        "journal_state": {"entries": [{"entry_id": "old"}]},
        "world_event_state": {"events": [{"event_id": "old"}]},
        "memory_state": {
            "service_memories": [{"memory_id": "old"}],
            "social_memories": [{"memory_id": "old-social"}],
            "npc_memories": {"npc:Bran": [{"memory_id": "old"}]},
            "rumors": [{"rumor_id": "old"}],
        },
        "player_state": {
            "location_id": "loc_tavern",
            "inventory_state": {
                "currency": {"gold": 9, "silver": 9, "copper": 9},
                "items": [{"item_id": "torch"}],
                "equipment": {"main_hand": {"item_id": "sword"}},
                "last_loot": [{"item_id": "coin"}],
            },
        },
    }

    cleaned = transcript._sanitize_manual_simulation_state_for_test(
        state,
        currency={"gold": 0, "silver": 2, "copper": 0},
    )

    assert cleaned["transaction_history"] == []
    assert cleaned["active_services"] == []
    assert cleaned["memory_rumors"] == []
    assert cleaned["relationship_state"] == {}
    assert cleaned["npc_emotion_state"] == {}
    assert cleaned["service_offer_state"] == {}
    assert cleaned["journal_state"] == {"entries": []}
    assert cleaned["world_event_state"] == {"events": []}
    assert cleaned["memory_state"]["service_memories"] == []
    assert cleaned["memory_state"]["social_memories"] == []
    assert cleaned["memory_state"]["npc_memories"] == {}
    assert cleaned["memory_state"]["rumors"] == []
    assert cleaned["player_state"]["inventory_state"]["items"] == []
    assert cleaned["player_state"]["inventory_state"]["equipment"] == {}
    assert cleaned["player_state"]["inventory_state"]["last_loot"] == []
    assert cleaned["player_state"]["inventory_state"]["currency"] == {
        "gold": 0,
        "silver": 2,
        "copper": 0,
    }