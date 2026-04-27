from app.rpg.session.ambient_tick_runtime import advance_autonomous_ambient_tick
from app.rpg.session.conversation_thread_runtime import (
    advance_conversation_threads_for_turn,
)
from app.rpg.world.conversation_pivots import detect_conversation_topic_pivot
from app.rpg.world.conversation_rumors import (
    expire_conversation_rumor_seeds,
    expire_conversation_world_signals,
    maybe_seed_rumor_from_signal,
)
from app.rpg.world.conversation_threads import (
    maybe_advance_conversation_thread,
    maybe_consume_pending_player_response,
)
from app.rpg.world.location_registry import set_current_location
from app.rpg.world.npc_goal_state import (
    active_goals_for_npc,
    dominant_goal_for_npc,
    seed_default_npc_goals,
)
from app.rpg.world.scene_activity_scheduler import maybe_schedule_scene_activity


def _settings(**overrides):
    settings = {
        "enabled": True,
        "autonomous_ticks_enabled": True,
        "frequency": "always",
        "conversation_chance_percent": 100,
        "min_ticks_between_conversations": 0,
        "thread_cooldown_ticks": 0,
        "allow_player_invited": True,
        "player_inclusion_chance_percent": 100,
        "allow_topic_pivots": True,
        "allow_npc_response_beats": True,
        "allow_npc_goal_influence": True,
        "allow_scene_activities": True,
        "scene_activity_interval_ticks": 1,
        "scene_activity_cooldown_ticks": 0,
    }
    settings.update(overrides)
    return settings


def test_klm_unbacked_dragon_lair_pivot_is_requested_but_rejected():
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


def test_klm_expired_rumor_seed_is_pruned_and_not_recreated_same_tick():
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


def test_npc_default_goals_are_bounded_and_location_scoped():
    state = {}
    set_current_location(state, "loc_tavern")

    result = seed_default_npc_goals(state, tick=12, location_id="loc_tavern")

    assert result["created_goal_ids"]
    bran_goals = active_goals_for_npc(state, "npc:Bran", tick=12, location_id="loc_tavern")
    assert 1 <= len(bran_goals) <= 4
    assert dominant_goal_for_npc(state, "npc:Bran", tick=12, location_id="loc_tavern")["kind"] in {
        "maintain_order",
        "gather_rumors",
    }


def test_scene_activity_scheduler_creates_bounded_activity_without_forbidden_mutation():
    state = {}
    set_current_location(state, "loc_tavern")

    result = maybe_schedule_scene_activity(
        state,
        tick=20,
        settings=_settings(
            allow_scene_activities=True,
            allow_scene_activity_world_events=True,
            allow_scene_activity_world_signals=True,
        ),
        force=True,
    )

    assert result["scheduled"] is True
    assert result["activity"]["npc_id"].startswith("npc:")
    assert state["scene_activity_state"]["recent"]
    assert "inventory_state" not in state
    assert "currency_state" not in state
    assert "transaction_state" not in state


def test_scene_activity_scheduler_respects_cooldown():
    state = {}
    set_current_location(state, "loc_tavern")
    settings = _settings(scene_activity_cooldown_ticks=10)

    first = maybe_schedule_scene_activity(state, tick=30, settings=settings, force=True)
    second = maybe_schedule_scene_activity(state, tick=31, settings=settings, force=False)

    assert first["scheduled"] is True
    assert second["scheduled"] is False
    assert second["reason"] in {"scene_activity_cooldown", "scene_activity_interval"}


def test_npc_goal_influences_player_joined_response_style_and_avoids_repeat_lines():
    state = {"quest_state": {"quests": []}}
    set_current_location(state, "loc_tavern")
    settings = _settings()

    invite = maybe_advance_conversation_thread(
        state,
        player_input="__ambient_tick_player_invited__",
        tick=40,
        settings=settings,
        autonomous=True,
        force=True,
        force_player_mode="player_invited",
    )
    assert invite["triggered"] is True

    first = maybe_consume_pending_player_response(
        state,
        player_input="What should I know?",
        tick=41,
        settings=settings,
    )
    assert first["triggered"] is True
    assert first["npc_response_style"] in {"guarded", "helpful", "friendly", "evasive", "annoyed"}
    first_line = first["npc_response_beat"]["line"]

    # Re-open a pending response on the same thread and ask again. The response
    # line should not repeat if avoid_repeated_npc_response_lines is enabled.
    thread = state["conversation_thread_state"]["threads"][0]
    state["conversation_thread_state"]["pending_player_response"] = {
        "thread_id": thread["thread_id"],
        "topic_id": thread["topic_id"],
        "prompt": "NPCs invite your response.",
        "created_tick": 42,
        "expires_tick": 45,
    }
    second = maybe_consume_pending_player_response(
        state,
        player_input="What else?",
        tick=42,
        settings=settings,
    )
    assert second["triggered"] is True
    assert second["npc_response_beat"]["line"] != first_line
    assert state["npc_goal_state"]["goals"]


def test_scene_activity_tick_does_not_force_conversation():
    state = {}
    runtime_state = {
        "runtime_settings": {
            "conversation_settings": {
                "enabled": True,
                "autonomous_ticks_enabled": True,
                "frequency": "off",
                "conversation_chance_percent": 0,
                "allow_scene_activities": True,
                "scene_activity_interval_ticks": 1,
                "scene_activity_cooldown_ticks": 0,
            }
        }
    }
    result = advance_autonomous_ambient_tick(
        player_input="__scene_activity_tick__",
        simulation_state=state,
        runtime_state=runtime_state,
        tick=100,
    )
    assert result["status"] == "scene_activity_tick"
    assert result["conversation_result"] == {}
    assert result["scene_activity_result"]["scheduled"] is True


def test_expire_conversation_world_signals_is_safe_on_fresh_state():
    state = {}
    result = expire_conversation_world_signals(
        state,
        runtime_state={},
        current_tick=10,
        settings={"max_signal_age_ticks": 3},
    )
    assert result["expired_count"] == 0
    assert result["remaining_thread_signal_count"] == 0
    assert result["remaining_rumor_signal_count"] == 0
    assert state["conversation_thread_state"]["world_signals"] == []
    assert state["conversation_rumor_state"]["conversation_world_signals"] == []


def test_expire_conversation_world_signals_expires_thread_state_signals():
    state = {
        "conversation_thread_state": {
            "world_signals": [
                {
                    "signal_id": "sig:old",
                    "kind": "rumor",
                    "created_tick": 5,
                    "expires_tick": 10,
                },
                {
                    "signal_id": "sig:new",
                    "kind": "rumor",
                    "created_tick": 9,
                    "expires_tick": 12,
                },
            ]
        }
    }
    result = expire_conversation_world_signals(
        state,
        runtime_state={},
        current_tick=10,
        settings={"max_signal_age_ticks": 3},
    )
    assert result["expired_count"] == 1
    assert [s["signal_id"] for s in state["conversation_thread_state"]["world_signals"]] == ["sig:new"]


def test_scene_activity_location_cooldown_blocks_immediate_second_tick():
    from app.rpg.session.ambient_tick_runtime import advance_autonomous_ambient_tick
    from app.rpg.world.location_registry import set_current_location

    state = {}
    set_current_location(state, "loc_tavern")
    runtime_state = {
        "runtime_settings": {
            "conversation_settings": {
                "allow_scene_activities": True,
                "scene_activity_cooldown_ticks": 5,
                "allow_scene_activity_world_events": False,
                "allow_scene_activity_world_signals": False,
            }
        }
    }
    first = advance_autonomous_ambient_tick(
        player_input="__scene_activity_tick__",
        simulation_state=state,
        runtime_state=runtime_state,
        tick=100,
    )
    second = advance_autonomous_ambient_tick(
        player_input="__scene_activity_tick__",
        simulation_state=state,
        runtime_state=runtime_state,
        tick=101,
    )
    assert first["scene_activity_result"]["scheduled"] is True
    assert second["scene_activity_result"]["scheduled"] is False
    assert second["scene_activity_result"]["reason"] == "scene_activity_location_cooldown"


def test_pending_response_takes_precedence_over_service_like_reply():
    state = {
        "conversation_thread_state": {
            "pending_player_response": {
                "thread_id": "conversation:loc_tavern:npc:Bran:npc:Mira",
                "topic_id": "topic:location:loc_tavern:mood",
                "prompt": "NPCs invite your response.",
                "created_tick": 10,
                "expires_tick": 20,
            },
            "threads": [
                {
                    "thread_id": "conversation:loc_tavern:npc:Bran:npc:Mira",
                    "participants": [
                        {"npc_id": "npc:Bran", "name": "Bran"},
                        {"npc_id": "npc:Mira", "name": "Mira"},
                    ],
                    "beats": [],
                    "status": "active",
                    "location_id": "loc_tavern",
                    "topic_id": "topic:location:loc_tavern:mood",
                    "topic_type": "location_smalltalk",
                    "topic_payload": {
                        "topic_id": "topic:location:loc_tavern:mood",
                        "topic_type": "location_smalltalk",
                        "title": "The tavern's mood",
                        "summary": "The tavern is busy.",
                        "allowed_facts": ["The tavern is busy."],
                    },
                }
            ],
        }
    }

    result = advance_conversation_threads_for_turn(
        player_input="What should I know about the room?",
        simulation_state=state,
        resolved_result={"action_type": "service_inquiry"},
        tick=11,
        runtime_state={"runtime_settings": {"conversation_settings": {"enabled": True}}},
    )

    assert result["triggered"] is True
    assert result["reason"] == "pending_player_response_consumed"
    assert state["conversation_thread_state"]["pending_player_response"] == {}


def test_expire_rumor_seed_prunes_seed_and_records_id():
    state = {
        "conversation_rumor_state": {
            "rumor_seeds": [
                {
                    "seed_id": "rumor_seed:test",
                    "expires_tick": 5,
                }
            ]
        },
        "conversation_thread_state": {
            "world_signals": [
                {
                    "signal_id": "signal:test",
                    "tick": 1,
                    "expires_tick": 5,
                }
            ]
        },
    }
    runtime_state = {}

    result = expire_conversation_world_signals(
        state,
        runtime_state=runtime_state,
        current_tick=5,
        settings={"max_signal_age_ticks": 3},
    )

    assert "rumor_seed:test" in result["expired_seed_ids"]
    assert "signal:test" in result["expired_signal_ids"]
    assert state["conversation_rumor_state"]["rumor_seeds"] == []
    assert state["conversation_thread_state"]["world_signals"] == []
