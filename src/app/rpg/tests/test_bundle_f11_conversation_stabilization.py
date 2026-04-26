from app.rpg.session.ambient_tick_runtime import advance_autonomous_ambient_tick
from app.rpg.session.state_normalization import _normalize_runtime_settings
from app.rpg.world.conversation_threads import maybe_advance_conversation_thread
from app.rpg.world.conversation_topics import (
    conversation_topics_for_state,
    select_conversation_topic,
)
from app.rpg.world.location_registry import set_current_location


def _runtime_settings(**conversation_overrides):
    settings = {
        "enabled": True,
        "autonomous_ticks_enabled": True,
        "frequency": "always",
        "conversation_chance_percent": 100,
        "min_ticks_between_conversations": 0,
        "thread_cooldown_ticks": 0,
    }
    settings.update(conversation_overrides)
    return {"runtime_settings": {"conversation_settings": settings}}


def test_runtime_settings_normalization_preserves_conversation_settings():
    normalized = _normalize_runtime_settings(
        {
            "response_length": "medium",
            "conversation_settings": {
                "enabled": True,
                "autonomous_ticks_enabled": True,
                "frequency": "always",
                "conversation_chance_percent": 100,
            },
        }
    )

    assert normalized["response_length"] == "medium"
    assert normalized["conversation_settings"]["autonomous_ticks_enabled"] is True
    assert normalized["conversation_settings"]["conversation_chance_percent"] == 100


def test_topics_skip_synthetic_room_environment_observe_memory():
    state = {
        "memory_state": {
            "social_memories": [
                {
                    "memory_id": "memory:observe:room",
                    "target_id": "npc:The Room/Environment",
                    "summary": "The player had a partial observe interaction with The Room/Environment.",
                    "action_type": "observe",
                }
            ]
        }
    }
    set_current_location(state, "loc_tavern")

    topics = conversation_topics_for_state(
        state,
        settings={"allow_memory_discussion": True},
    )

    assert all(topic.get("topic_type") != "memory" for topic in topics)
    assert select_conversation_topic(
        state,
        settings={"allow_memory_discussion": True},
    )["topic_type"] == "location_smalltalk"


def test_quest_topics_support_active_quests_shape():
    state = {
        "quest_state": {
            "active_quests": [
                {
                    "id": "quest:old_mill",
                    "title": "Trouble near the Old Mill",
                    "summary": "Armed figures have been seen near the old mill road.",
                    "status": "active",
                    "location_id": "loc_tavern",
                }
            ]
        }
    }
    set_current_location(state, "loc_tavern")

    topic = select_conversation_topic(
        state,
        settings={"allow_quest_discussion": True},
        forced_topic_type="quest",
    )

    assert topic["topic_type"] == "quest"
    assert topic["source_id"] == "quest:old_mill"


def test_world_signal_disabled_does_not_append_empty_thread_signal():
    state = {}
    set_current_location(state, "loc_tavern")

    result = maybe_advance_conversation_thread(
        state,
        player_input="I wait and listen",
        tick=10,
        settings={
            "enabled": True,
            "allow_world_signals": False,
            "allow_world_events": False,
            "thread_cooldown_ticks": 0,
        },
    )

    assert result["triggered"] is True
    assert result["world_signal"] == {}
    assert result["world_event"] == {}

    thread = state["conversation_thread_state"]["threads"][0]
    assert thread["world_signals"] == []
    assert state.get("world_event_state", {}).get("events", []) == []


def test_max_active_threads_blocks_new_thread():
    state = {
        "conversation_thread_state": {
            "threads": [],
            "active_thread_ids": ["conversation:other-location:npc:a:npc:b"],
            "world_signals": [],
            "debug": {},
        }
    }
    set_current_location(state, "loc_tavern")

    result = maybe_advance_conversation_thread(
        state,
        player_input="I wait and listen",
        tick=11,
        settings={"enabled": True, "max_active_threads": 1},
    )

    assert result["triggered"] is False
    assert result["reason"] == "max_active_threads_reached"


def test_forced_ambient_tick_uses_supplied_authoritative_tick():
    state = {}
    set_current_location(state, "loc_tavern")

    result = advance_autonomous_ambient_tick(
        player_input="__ambient_tick_player_invited__",
        simulation_state=state,
        runtime_state=_runtime_settings(
            allow_player_invited=True,
            player_inclusion_chance_percent=100,
            pending_response_timeout_ticks=3,
            allow_world_signals=True,
            allow_world_events=True,
        ),
        tick=527,
    )

    conversation = result["conversation_result"]

    assert result["applied"] is True
    assert conversation["beat"]["tick"] == 527
    assert conversation["world_signal"]["tick"] == 527
    assert conversation["world_event"]["tick"] == 527
    assert conversation["player_participation"]["created_tick"] == 527
    assert conversation["player_participation"]["expires_tick"] == 530