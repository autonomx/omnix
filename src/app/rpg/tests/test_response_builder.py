"""Tests for response builder functionality."""


def test_response_builder_preserves_living_world_and_recall_debug_fields():
    from app.rpg.session.response_builder import _attach_living_world_debug_fields

    payload = {
        "narration_debug": {
            "recalled_service_memories": [{"memory_id": "memory:prior"}],
            "service_memory_recall_debug": {"count": 1},
        },
        "resolved_result": {
            "service_application": {
                "memory_entry": {"memory_id": "memory:current"},
                "social_effects": {"relationship_key": "npc:Elara::player"},
                "stock_update": {"offer_id": "elara_torch"},
            },
            "memory_state": {"service_memories": [{"memory_id": "memory:current"}]},
            "relationship_state": {"npc:Elara::player": {"axes": {"familiarity": 1}}},
            "npc_emotion_state": {"npc:Elara": {"dominant_emotion": "neutral"}},
            "service_offer_state": {"offers": {"elara_torch": {"stock_remaining": 2}}},
        },
    }

    out = _attach_living_world_debug_fields(payload)

    assert out["living_world_debug"]["memory_entry"]["memory_id"] == "memory:current"
    assert out["living_world_debug"]["social_effects"]["relationship_key"] == "npc:Elara::player"
    assert out["living_world_debug"]["stock_update"]["offer_id"] == "elara_torch"
    assert out["recalled_service_memories"][0]["memory_id"] == "memory:prior"
    assert out["service_memory_recall_debug"]["count"] == 1
    assert out["memory_state"]["service_memories"][0]["memory_id"] == "memory:current"