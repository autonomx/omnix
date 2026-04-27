from app.rpg.world.conversation_pivots import detect_conversation_topic_pivot
from app.rpg.world.conversation_rumors import (
    expire_conversation_rumor_seeds,
    expire_conversation_world_signals,
    maybe_seed_rumor_from_signal,
)


def test_old_conversation_world_signals_expire():
    # assume some test code
    pass


def test_unbacked_dragon_lair_pivot_is_requested_but_rejected():
    state = {}
    response = detect_conversation_topic_pivot(
        state,
        player_input="Tell me about the dragon lair hidden in the northern mountains.",
        current_topic={"topic_id": "topic:location:loc_tavern:mood", "topic_type": "location_smalltalk"},
        settings={"allow_topic_pivots": True},
    )

    assert response["requested"] is True
    assert response["accepted"] is False
    assert response["pivot_rejected_reason"] == "no_backed_topic_found"
    assert "dragon" in response["requested_topic_hint"]


def test_expired_rumor_seed_is_pruned_and_not_recreated_same_tick():
    state = {}
    signal = {
        "signal_id": "signal:old-mill:1",
        "kind": "quest_interest",
        "topic_id": "topic:quest:old_mill",
        "topic_type": "quest",
        "location_id": "loc_tavern",
        "summary": "There is talk of armed figures near the old mill road.",
        "source_thread_id": "thread:old-mill",
    }
    settings = {"allow_rumor_propagation": True, "max_signal_age_ticks": 1}

    created = maybe_seed_rumor_from_signal(state, runtime_state={}, signal=signal, tick=10, settings=settings)
    assert created["created"] is True
    assert state["conversation_rumor_state"]["rumor_seeds"][0]["expires_tick"] == 11

    expired = expire_conversation_rumor_seeds(state, current_tick=11, settings=settings)
    assert expired["expired_seed_count"] == 1
    assert state["conversation_rumor_state"]["rumor_seeds"] == []

    recreated = maybe_seed_rumor_from_signal(state, runtime_state={}, signal={**signal, "signal_id": "signal:old-mill:2"}, tick=11, settings=settings)
    assert recreated["created"] is False
    assert recreated["reason"] == "rumor_seed_expired_this_tick"


def test_backed_topic_pivot_returns_full_selected_topic():
    from app.rpg.world.conversation_pivots import detect_conversation_topic_pivot
    from app.rpg.world.location_registry import set_current_location

    state = {
        "quest_state": {
            "quests": [
                {
                    "quest_id": "quest:old_mill_bandits",
                    "title": "Trouble near the Old Mill",
                    "summary": "There is talk of armed figures near the old mill road at night.",
                    "status": "active",
                    "location_id": "loc_tavern",
                }
            ]
        }
    }
    set_current_location(state, "loc_tavern")
    response = detect_conversation_topic_pivot(
        state,
        "What can you tell me about the trouble at the old mill road?",
        current_topic={"topic_id": "topic:location:loc_tavern:mood", "topic_type": "location_smalltalk"},
        settings={"allow_quest_discussion": True},
    )
    assert response["requested"] is True
    assert response["accepted"] is True
    assert response["selected_topic_type"] == "quest"
    assert response["selected_topic"]
    assert response["pivot_rejected_reason"] == ""