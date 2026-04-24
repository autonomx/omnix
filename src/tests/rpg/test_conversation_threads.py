from app.rpg.ai.conversation_threads import (
    add_thread_line,
    build_conversation_thread_prompt_context,
    expire_conversation_threads,
    normalize_conversation_threads,
    seed_or_update_thread,
)


def test_conversation_thread_persists_and_records_lines():
    runtime_state = seed_or_update_thread(
        {},
        kind="player_interaction",
        participants=["player", "bran"],
        topic={
            "key": "room_rental",
            "type": "player_interaction",
            "summary": "The player is asking Bran about renting a room.",
        },
        current_tick=10,
        location_id="rusty_flagon",
        scene_id="tavern",
    )

    assert len(runtime_state["conversation_threads"]) == 1
    thread_id = runtime_state["conversation_threads"][0]["thread_id"]

    runtime_state = add_thread_line(
        runtime_state,
        thread_id=thread_id,
        speaker_id="bran",
        speaker_name="Bran the Innkeeper",
        target_id="player",
        target_name="you",
        text="The best room is upstairs, but it costs more.",
        kind="answer",
        current_tick=11,
    )

    context = build_conversation_thread_prompt_context(
        runtime_state,
        current_tick=11,
        limit=4,
    )

    assert len(context) == 1
    assert context[0]["recent_lines"][0]["speaker_id"] == "bran"
    assert "best room" in context[0]["recent_lines"][0]["text"]


def test_conversation_threads_expire_after_ttl():
    runtime_state = seed_or_update_thread(
        {},
        kind="npc_to_npc",
        participants=["bran", "elara"],
        topic={
            "key": "rumor",
            "summary": "Bran and Elara discuss a rumor.",
        },
        current_tick=1,
    )

    runtime_state = expire_conversation_threads(runtime_state, current_tick=100)

    assert normalize_conversation_threads(runtime_state)["conversation_threads"] == []
