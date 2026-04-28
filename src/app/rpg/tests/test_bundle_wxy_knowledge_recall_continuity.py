def test_recall_request_can_be_consumed_without_pending_response():
    from app.rpg.world.conversation_threads import maybe_advance_conversation_thread
    from app.rpg.world.location_registry import set_current_location
    from app.rpg.world.npc_history_state import add_npc_history_entry
    from app.rpg.world.npc_knowledge_state import add_npc_knowledge_from_topic
    from app.rpg.world.npc_presence_runtime import update_present_npcs_for_location

    state = {"location_state": {"current_location_id": "loc_tavern"}}
    set_current_location(state, "loc_tavern")
    update_present_npcs_for_location(state, location_id="loc_tavern", tick=10)

    add_npc_history_entry(
        state,
        npc_id="npc:Bran",
        kind="player_conversation_reply",
        summary="The player asked Bran about the old mill road.",
        topic_id="topic:quest:old_mill",
        tick=10,
        importance=2,
    )
    add_npc_knowledge_from_topic(
        state,
        npc_id="npc:Bran",
        topic={
            "topic_id": "topic:quest:old_mill",
            "topic_type": "quest",
            "summary": "There is talk of armed figures near the old mill road.",
            "source_id": "quest:old_mill",
            "source_kind": "quest",
        },
        tick=10,
    )

    result = maybe_advance_conversation_thread(
        state,
        player_input="Do you remember what I asked before?",
        tick=11,
        settings={
            "enabled": True,
            "npc_dialogue_recall_enabled": True,
            "allow_world_signals": False,
            "allow_world_events": False,
        },
    )

    assert result["triggered"] is True
    assert result["reason"] == "recall_request_consumed"
    assert result["npc_response_beat"]["dialogue_recall"]["selected"] is True
    assert result["recalled_history_ids"] or result["recalled_knowledge_ids"]
    assert "remember" in result["npc_response_beat"]["line"].lower()


def test_forced_player_invited_reused_thread_creates_pending_response():
    from app.rpg.session.ambient_tick_runtime import advance_autonomous_ambient_tick
    from app.rpg.world.location_registry import set_current_location

    state = {
        "conversation_thread_state": {
            "threads": [
                {
                    "thread_id": "conversation:loc_tavern:npc:Bran:npc:Mira",
                    "participants": [
                        {"npc_id": "npc:Bran", "name": "Bran"},
                        {"npc_id": "npc:Mira", "name": "Mira"},
                    ],
                    "location_id": "loc_tavern",
                    "topic_id": "topic:location:loc_tavern:mood",
                    "topic_type": "location_smalltalk",
                    "topic": "The tavern's mood",
                    "topic_payload": {
                        "topic_id": "topic:location:loc_tavern:mood",
                        "topic_type": "location_smalltalk",
                        "title": "The tavern's mood",
                        "summary": "The tavern is busy with travelers, food, and low conversation.",
                    },
                    "participation_mode": "overheard",
                    "player_participation": {
                        "included": False,
                        "mode": "overheard",
                        "pending_response": False,
                    },
                    "beats": [],
                    "status": "active",
                    "created_tick": 10,
                    "updated_tick": 10,
                }
            ],
            "active_thread_ids": ["conversation:loc_tavern:npc:Bran:npc:Mira"],
            "pending_player_response": {},
        }
    }
    set_current_location(state, "loc_tavern")

    runtime_state = {
        "runtime_settings": {
            "conversation_settings": {
                "enabled": True,
                "autonomous_ticks_enabled": True,
                "allow_player_invited": True,
                "player_inclusion_chance_percent": 100,
                "conversation_chance_percent": 100,
                "frequency": "always",
                "thread_cooldown_ticks": 0,
                "min_ticks_between_conversations": 0,
            }
        }
    }

    result = advance_autonomous_ambient_tick(
        player_input="__ambient_tick_player_invited__",
        simulation_state=state,
        runtime_state=runtime_state,
        tick=11,
    )

    assert result["forced_player_invited"] is True
    assert result["forced_player_invited_failed"] is False

    conversation = result["conversation_result"]
    assert conversation["triggered"] is True
    assert conversation["participation_mode"] == "player_invited"
    assert conversation["player_participation"]["pending_response"] is True

    pending = state["conversation_thread_state"]["pending_player_response"]
    assert pending
    assert pending["thread_id"]
    assert pending["created_tick"] == 11