from app.rpg.memory.social_effects import apply_general_social_effects


def test_social_interaction_updates_relationship_emotion_and_memory():
    state = {}
    result = {
        "action_type": "social_activity",
        "outcome": "success",
        "margin": 2,
        "target_id": "npc:Bran",
        "target_name": "Bran",
    }

    effects = apply_general_social_effects(state, result, tick=42)

    assert effects["relationship_key"] == "npc:Bran::player"
    assert state["relationship_state"]["npc:Bran::player"]["axes"]["familiarity"] > 0
    assert "npc:Bran" in state["npc_emotion_state"]
    assert state["memory_state"]["social_memories"][0]["owner_id"] == "npc:Bran"


def test_service_result_is_ignored_by_general_social_effects():
    state = {}
    result = {
        "action_type": "service_inquiry",
        "target_id": "npc:Bran",
        "target_name": "Bran",
        "service_result": {"matched": True},
    }

    assert apply_general_social_effects(state, result, tick=1) == {}
    assert state == {}