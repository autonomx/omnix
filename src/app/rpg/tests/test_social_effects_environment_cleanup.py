from app.rpg.memory.social_effects import apply_social_effects


def _apply(target_id: str, target_name: str, *, action_type: str = "observe"):
    simulation_state = {}
    result = apply_social_effects(
        simulation_state=simulation_state,
        resolved_result={
            "action_type": action_type,
            "semantic_action_type": action_type,
            "semantic_family": "ambient" if action_type in {"observe", "wait", "listen", "ambient_wait"} else "social",
            "target_id": target_id,
            "target_name": target_name,
            "summary": f"The player had a partial {action_type} interaction with {target_name}.",
            "success": True,
        },
        tick=42,
    )
    return result, simulation_state


def _assert_no_social_state(simulation_state):
    memory_state = simulation_state.get("memory_state", {})
    assert not memory_state.get("social_memories")

    relationship_state = simulation_state.get("relationship_state", {})
    assert not relationship_state

    emotion_state = simulation_state.get("npc_emotion_state", {})
    assert not emotion_state


def test_social_effects_skip_room_environment_placeholder_memory():
    result, state = _apply("npc:The Room/Environment", "The Room/Environment")

    assert result.get("skipped") is True
    assert result.get("reason") in {
        "synthetic_social_target",
        "ambient_non_npc_social_target",
        "unknown_or_synthetic_npc_target",
    }
    _assert_no_social_state(state)


def test_social_effects_skip_tavern_atmosphere_placeholder_memory():
    result, state = _apply("npc:The Tavern Atmosphere", "The Tavern Atmosphere")

    assert result.get("skipped") is True
    assert result.get("reason") in {
        "synthetic_social_target",
        "ambient_non_npc_social_target",
        "unknown_or_synthetic_npc_target",
    }
    _assert_no_social_state(state)


def test_social_effects_skip_environment_npcs_general_memory():
    result, state = _apply("Environment/NPCs (General)", "Environment/NPCs (General)")

    assert result.get("skipped") is True
    _assert_no_social_state(state)


def test_social_effects_skip_plain_environment_target():
    result, state = _apply("environment", "environment")

    assert result.get("skipped") is True
    _assert_no_social_state(state)


def test_social_effects_valid_known_npc_still_allowed():
    result, state = _apply("npc:Bran", "Bran", action_type="social_activity")

    assert result.get("skipped") is not True

    memory_state = state.get("memory_state", {})
    relationship_state = state.get("relationship_state", {})
    emotion_state = state.get("npc_emotion_state", {})

    assert memory_state.get("social_memories") or relationship_state or emotion_state
    assert "npc:The Tavern Atmosphere" not in str(state)
    assert "npc:The Room/Environment" not in str(state)