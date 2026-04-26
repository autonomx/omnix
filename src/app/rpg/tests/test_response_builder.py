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


def test_build_apply_turn_response_keeps_authoritative_structure_with_narration_overlay():
    from app.rpg.session.response_builder import build_apply_turn_response

    authoritative_result = {
        "session": {"session_id": "manual_test_session"},
        "turn_contract": {"contract_version": "turn_contract_v1"},
        "authoritative": {
            "turn_id": "turn:5",
            "tick": 5,
            "resolved_result": {
                "memory_state": {
                    "service_memories": [{"memory_id": "memory:current"}],
                },
                "social_living_world_effects": {
                    "memory_entry": {"memory_id": "memory:current"},
                },
            },
            "combat_result": {"status": "idle"},
            "xp_result": {"player_xp": 1},
            "skill_xp_result": {"awards": {}},
            "level_up": [],
            "skill_level_ups": [],
            "summary": "summary",
            "presentation": {"available_actions": []},
            "response_length": "short",
            "deterministic_fallback_narration": "fallback narration",
        },
        "result": {
            "narration": "llm narration",
            "raw_llm_narrative": {"narration": "llm narration"},
            "used_llm": True,
            "narration_status": "completed",
            "narration_debug": {
                "recalled_npc_memories": [{"memory_id": "memory:prior"}],
                "npc_memory_recall_debug": {"count": 1},
            },
        },
    }

    out = build_apply_turn_response(authoritative_result)

    assert out["result"]["turn_id"] == "turn:5"
    assert out["result"]["tick"] == 5
    assert out["result"]["resolved_result"]["memory_state"]["service_memories"][0]["memory_id"] == "memory:current"
    assert out["result"]["narration"] == "llm narration"
    assert out["result"]["used_llm"] is True
    assert out["result"]["recalled_npc_memories"][0]["memory_id"] == "memory:prior"
    assert out["result"]["npc_memory_recall_debug"]["count"] == 1
    assert out["result"]["social_living_world_effects"]["memory_entry"]["memory_id"] == "memory:current"