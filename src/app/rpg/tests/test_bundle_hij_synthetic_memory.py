"""Synthetic NPC and memory cleanup coverage for Bundle H-I-J.1."""

from app.rpg.memory.social_effects import apply_general_social_effects
from app.rpg.tests.test_bundle_hij_manual_scenarios import (
    _assert_no_synthetic_npc_in_social_state,
    _invite_player,
    _player_reply,
    _runtime_state,
    add_rumor_seed,
    advance_autonomous_ambient_tick,
    record_player_joined_conversation,
    set_current_location,
    _is_synthetic_npc_participant,
)


def test_synthetic_npc_guard_identifies_room_environment():
    """_is_synthetic_npc_participant must block npc:The Room/Environment."""
    assert _is_synthetic_npc_participant({"id": "npc:The Room/Environment"})
    assert _is_synthetic_npc_participant({"id": "npc:The Room/Environment", "name": "The Room/Environment"})


def test_synthetic_npc_guard_identifies_environment_general():
    assert _is_synthetic_npc_participant({"id": "npc:Environment/NPCs (General)"})
    assert _is_synthetic_npc_participant({"name": "Environment/NPCs (General)", "id": "npc:Environment/NPCs (General)"})


def test_synthetic_npc_guard_identifies_ambient_wait_target():
    assert _is_synthetic_npc_participant({"id": "ambient_wait"})
    assert _is_synthetic_npc_participant({"id": "npc:ambient_wait"})


def test_synthetic_npc_guard_allows_real_npc():
    assert not _is_synthetic_npc_participant({"id": "npc:Bran", "name": "Bran"})
    assert not _is_synthetic_npc_participant({"id": "npc:Mira", "name": "Mira"})
    assert not _is_synthetic_npc_participant({"id": "npc:Elara", "name": "Elara"})


def test_synthetic_npc_guard_blocks_non_npc_prefixed():
    """IDs without npc: prefix are synthetic (except empty ID, handled upstream)."""
    assert _is_synthetic_npc_participant({"id": "room:environment"})
    assert _is_synthetic_npc_participant({"id": "environment:general"})


def test_synthetic_npc_does_not_appear_in_social_state_after_player_join():
    """Regression: record_player_joined_conversation must skip synthetic participants."""
    state = {}
    synthetic_thread = {
        "thread_id": "conversation:loc_tavern:synthetic",
        "participants": [
            {"id": "npc:The Room/Environment", "name": "The Room/Environment"},
            {"id": "npc:Bran", "name": "Bran"},
        ],
    }
    fake_response = {"beat_id": "beat:test", "line": "I am watching."}
    topic = {"topic_id": "topic:location:loc_tavern:mood", "topic_type": "location_smalltalk"}

    record_player_joined_conversation(
        state,
        tick=1,
        thread=synthetic_thread,
        player_response=fake_response,
        topic=topic,
    )

    npc_state = state["conversation_social_state"]["npc_state"]
    assert "npc:The Room/Environment" not in npc_state, (
        "npc:The Room/Environment must NOT appear in conversation_social_state"
    )
    assert "npc:Bran" in npc_state, "Real NPC Bran must still be recorded"
    _assert_no_synthetic_npc_in_social_state(state, label="regression_synthetic_block")


def test_synthetic_npc_skipped_ids_in_debug():
    """The debug block should record which synthetic IDs were skipped."""
    state = {}
    synthetic_thread = {
        "thread_id": "t1",
        "participants": [
            {"id": "npc:The Room/Environment", "name": "The Room/Environment"},
        ],
    }
    record_player_joined_conversation(
        state,
        tick=5,
        thread=synthetic_thread,
        player_response={"beat_id": "b1", "line": "test"},
        topic={"topic_id": "tid", "topic_type": "location_smalltalk"},
    )
    debug = state["conversation_social_state"]["debug"]
    assert "skipped_synthetic_ids" in debug
    assert "npc:The Room/Environment" in debug["skipped_synthetic_ids"]


def test_general_social_effects_skip_room_environment_memory():
    """Regression: ambient observe must not create relationship/emotion/social memory for the room."""
    state = {}

    result = apply_general_social_effects(
        state,
        {
            "action_type": "observe",
            "semantic_action_type": "ambient_wait",
            "semantic_family": "ambient",
            "activity_label": "observe",
            "target_id": "npc:The Room/Environment",
            "target_name": "The Room/Environment",
            "outcome": "failure",
            "service_result": {"matched": False},
        },
        tick=1,
    )

    assert result.get("skipped") is True
    assert result.get("reason") == "synthetic_social_target"
    assert state.get("relationship_state", {}) == {}
    assert state.get("npc_emotion_state", {}) == {}
    assert state.get("memory_state", {}).get("social_memories", []) == []


def test_forced_player_invited_overrides_existing_thread_mode():
    state = {}
    set_current_location(state, "loc_tavern")
    rt = _runtime_state(
        allow_player_invited=True,
        player_inclusion_chance_percent=100,
        thread_cooldown_ticks=0,
    )

    first = advance_autonomous_ambient_tick(
        player_input="__ambient_tick__",
        simulation_state=state,
        runtime_state=rt,
        tick=10,
    )
    assert first["applied"] is True

    second = advance_autonomous_ambient_tick(
        player_input="__ambient_tick_player_invited__",
        simulation_state=state,
        runtime_state=rt,
        tick=11,
    )

    assert second["applied"] is True
    conv = second["conversation_result"]
    assert conv["player_participation"]["mode"] == "player_invited"
    assert conv["player_participation"]["pending_response"] is True
    assert state["conversation_thread_state"]["pending_player_response"]


def test_live_conversation_does_not_leak_synthetic_npcs():
    """Full conversation flow from invite through player reply must not pollute social state."""
    state = {}
    set_current_location(state, "loc_tavern")
    rt = _runtime_state()
    _invite_player(state, rt, tick=1)
    _player_reply(state, rt, "Anything of interest here?", tick=2)

    _assert_no_synthetic_npc_in_social_state(state, label="live_flow_regression")


def test_no_observe_or_ambient_wait_in_memory_topics():
    """Synthetic observe/ambient_wait entries must not appear as memory topics."""
    from app.rpg.world.conversation_topics import conversation_topics_for_state
    state = {
        "memory_state": {
            "social_memories": [
                {
                    "memory_id": "memory:observe:room",
                    "actor_id": "player",
                    "target_id": "npc:The Room/Environment",
                    "summary": "The player had a partial observe interaction with The Room/Environment.",
                    "action_type": "observe",
                },
                {
                    "memory_id": "memory:observe:ambient",
                    "actor_id": "player",
                    "target_id": "ambient_wait",
                    "summary": "The player waited and observed the ambient environment.",
                    "action_type": "ambient_wait",
                },
                {
                    # Real NPC memory — this SHOULD appear
                    "memory_id": "memory:bran:greeting",
                    "actor_id": "npc:Bran",
                    "target_id": "player",
                    "summary": "Bran greeted the player warmly.",
                    "action_type": "greet",
                },
            ]
        }
    }
    set_current_location(state, "loc_tavern")
    topics = conversation_topics_for_state(state, settings={"allow_memory_discussion": True})
    for topic in topics:
        if topic["topic_type"] == "memory":
            source_id = topic.get("source_id", "")
            assert "room/environment" not in source_id.lower(), (
                f"Room/Environment memory leaked into topics: {topic}"
            )
            assert "ambient_wait" not in source_id.lower(), (
                f"ambient_wait memory leaked into topics: {topic}"
            )
    memory_topics = [t for t in topics if t["topic_type"] == "memory"]
    bran_topics = [t for t in memory_topics if "bran" in t.get("source_id", "").lower()]
    assert bran_topics, "Real NPC memory (Bran) must appear in topics"


def test_general_social_effects_skip_location_general_placeholder_memory():
    """Regression: location placeholder NPCs like npc:The Tavern (General) are not real NPCs."""
    state = {}

    result = apply_general_social_effects(
        state,
        {
            "action_type": "observe",
            "semantic_action_type": "ambient_wait",
            "semantic_family": "ambient",
            "activity_label": "observe",
            "target_id": "",
            "target_name": "The Tavern (General)",
            "outcome": "success",
        },
        tick=527,
    )

    assert result.get("skipped") is True
    assert result.get("reason") == "synthetic_social_target"
    assert state.get("relationship_state", {}) == {}
    assert state.get("npc_emotion_state", {}) == {}
    assert state.get("memory_state", {}).get("social_memories", []) == []


def test_add_rumor_seed_purges_expired_seed_before_dedup():
    state = {}
    settings = {
        "allow_rumor_propagation": True,
        "max_rumor_seeds": 16,
        "max_rumor_mentions_per_location": 4,
        "max_signal_age_ticks": 3,
    }

    first = add_rumor_seed(
        state,
        signal={
            "signal_id": "sig:old",
            "kind": "quest_interest",
            "strength": 1,
            "topic_id": "topic:quest:quest:old_mill_bandits",
            "topic_type": "quest",
        },
        topic={
            "topic_id": "topic:quest:quest:old_mill_bandits",
            "topic_type": "quest",
        },
        tick=526,
        location_id="loc_tavern",
        settings=settings,
    )

    assert first["expires_tick"] == 529

    # At the expiry boundary, the old seed must be purged before dedup.
    second = add_rumor_seed(
        state,
        signal={
            "signal_id": "sig:new",
            "kind": "quest_interest",
            "strength": 1,
            "topic_id": "topic:quest:quest:old_mill_bandits",
            "topic_type": "quest",
        },
        topic={
            "topic_id": "topic:quest:quest:old_mill_bandits",
            "topic_type": "quest",
        },
        tick=529,
        location_id="loc_tavern",
        settings=settings,
    )

    seeds = state["rumor_propagation_state"]["rumor_seeds"]

    assert second
    assert len(seeds) == 1
    assert seeds[0]["created_tick"] == 529
    assert seeds[0]["seed_id"].startswith("rumor_seed:529:")
    assert not any(seed["seed_id"].startswith("rumor_seed:526:") for seed in seeds)
