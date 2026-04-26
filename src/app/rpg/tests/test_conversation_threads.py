from app.rpg.world.conversation_threads import (
    get_conversation_thread_state,
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
