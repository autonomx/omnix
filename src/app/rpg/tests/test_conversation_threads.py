from app.rpg.world.conversation_threads import (
    maybe_advance_conversation_thread,
    select_conversation_participants,
)
from app.rpg.world.location_registry import set_current_location


def test_select_conversation_participants_uses_present_npcs_only():
    state = {}
    set_current_location(state, "loc_tavern")

    participants = select_conversation_participants(state)

    assert len(participants) == 2
    assert {p["id"] for p in participants} == {"npc:Bran", "npc:Mira"}


def test_waiting_in_tavern_creates_bounded_conversation_thread():
    state = {}
    set_current_location(state, "loc_tavern")

    result = maybe_advance_conversation_thread(
        state,
        player_input="I wait and listen to the room",
        tick=10,
    )

    assert result["triggered"] is True
    assert result["beat"]["speaker_id"] in {"npc:Bran", "npc:Mira"}
    assert result["world_signal"]["kind"] == "rumor_interest"
    assert state["conversation_thread_state"]["threads"]
    assert state["conversation_thread_state"]["world_signals"]
    assert state["world_event_state"]["events"][0]["kind"] == "npc_conversation"
    assert "Bran " not in result["beat"]["line"]
    assert "Mira " not in result["beat"]["line"]


def test_non_wait_turn_does_not_trigger_conversation():
    state = {}
    set_current_location(state, "loc_tavern")

    result = maybe_advance_conversation_thread(
        state,
        player_input="I buy a meal from Bran",
        tick=11,
    )

    assert result["triggered"] is False
    assert result["reason"] == "not_wait_or_listen_turn"


def test_conversation_does_not_mutate_player_resources_or_journal():
    state = {
        "player_state": {
            "inventory_state": {
                "currency": {"gold": 0, "silver": 5, "copper": 0},
                "items": [{"item_id": "torch"}],
                "equipment": {},
                "last_loot": [],
            }
        },
        "journal_state": {"entries": []},
        "transaction_history": [],
    }
    set_current_location(state, "loc_tavern")

    before_currency = dict(state["player_state"]["inventory_state"]["currency"])
    before_items = list(state["player_state"]["inventory_state"]["items"])

    result = maybe_advance_conversation_thread(
        state,
        player_input="I wait and listen",
        tick=12,
    )

    assert result["triggered"] is True
    assert state["player_state"]["inventory_state"]["currency"] == before_currency
    assert state["player_state"]["inventory_state"]["items"] == before_items
    assert state["journal_state"]["entries"] == []
    assert state["transaction_history"] == []


def test_npc_to_npc_thread_id_is_stable_for_reversed_speaker_listener():
    from app.rpg.world.conversation_threads import maybe_advance_conversation_thread
    from app.rpg.world.location_registry import set_current_location

    state = {
        "quest_state": {
            "quests": [
                {
                    "quest_id": "quest:old_mill_bandits",
                    "title": "Trouble near the Old Mill",
                    "summary": "There is talk of armed figures near the old mill road.",
                    "status": "active",
                    "location_id": "loc_tavern",
                }
            ]
        },
        "present_npc_state": {
            "loc_tavern": ["npc:Bran", "npc:Mira"]
        },
    }
    set_current_location(state, "loc_tavern")

    first = maybe_advance_conversation_thread(
        state,
        player_input="__ambient_tick_quest__",
        tick=100,
        settings={
            "enabled": True,
            "conversation_director_enabled": True,
            "allow_world_signals": False,
            "allow_world_events": False,
            "thread_cooldown_ticks": 0,
            "max_beats_per_thread": 10,
        },
        autonomous=True,
        force=True,
        forced_topic_type="quest",
    )

    second = maybe_advance_conversation_thread(
        state,
        player_input="__ambient_tick_quest__",
        tick=101,
        settings={
            "enabled": True,
            "conversation_director_enabled": True,
            "allow_world_signals": False,
            "allow_world_events": False,
            "thread_cooldown_ticks": 0,
            "max_beats_per_thread": 10,
        },
        autonomous=True,
        force=True,
        forced_topic_type="quest",
    )

    assert first["triggered"] is True
    assert second["triggered"] is True

    threads = state["conversation_thread_state"]["threads"]
    bran_mira_threads = [
        thread
        for thread in threads
        if set(
            participant.get("id")
            for participant in thread.get("participants", [])
        ) == {"npc:Bran", "npc:Mira"}
    ]

    assert len(bran_mira_threads) == 1
    assert len(bran_mira_threads[0]["beats"]) >= 2
