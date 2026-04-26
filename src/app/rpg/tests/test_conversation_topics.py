from app.rpg.world.conversation_topics import (
    conversation_topics_for_state,
    select_conversation_topic,
)
from app.rpg.world.location_registry import set_current_location


def test_location_topic_is_fallback():
    state = {}
    set_current_location(state, "loc_tavern")

    topics = conversation_topics_for_state(state)
    assert topics
    assert any(topic["topic_type"] == "location_smalltalk" for topic in topics)


def test_excludes_current_turn_event_ids():
    state = {
        "world_event_state": {
            "events": [
                {
                    "event_id": "world:event:service:1",
                    "kind": "service_inquiry",
                    "title": "Service inquiry",
                    "summary": "Bran checked lodging options.",
                }
            ]
        }
    }
    set_current_location(state, "loc_tavern")

    topic = select_conversation_topic(
        state,
        settings={"allow_event_discussion": True},
        forced_topic_type="recent_event",
        exclude_event_ids=["world:event:service:1"],
    )

    assert topic.get("topic_type") != "recent_event"


def test_conversation_topics_skip_npc_conversation_events():
    state = {
        "world_event_state": {
            "events": [
                {
                    "event_id": "world:event:npc_conversation:1",
                    "kind": "npc_conversation",
                    "title": "NPC conversation",
                    "summary": "Bran speaks with Mira about the tavern.",
                }
            ]
        }
    }
    set_current_location(state, "loc_tavern")

    topic = select_conversation_topic(
        state,
        settings={"allow_event_discussion": True},
        forced_topic_type="recent_event",
    )

    assert topic.get("topic_type") != "recent_event"