from app.rpg.party.companion_commands import maybe_apply_companion_command
from app.rpg.party.companion_presence import sync_active_companions_to_player_location


def _state_with_bran_companion():
    return {
        "location_id": "loc_tavern",
        "player_state": {
            "location_id": "loc_tavern",
            "party_state": {
                "max_size": 3,
                "companions": [
                    {
                        "npc_id": "npc:Bran",
                        "name": "Bran",
                        "role": "companion",
                        "status": "active",
                        "follow_mode": "following_player",
                        "location_id": "loc_tavern",
                        "identity_arc": "revenge_after_losing_tavern",
                        "current_role": "Displaced tavern keeper",
                    }
                ],
            },
        },
    }


def _bran(state):
    return state["player_state"]["party_state"]["companions"][0]


def test_stay_command_sets_waiting_here():
    state = _state_with_bran_companion()

    result = maybe_apply_companion_command(
        state,
        player_input="Bran, stay here.",
        tick=1,
    )

    assert result["recognized"] is True
    assert result["accepted"] is True
    assert result["command"] == "stay"

    bran = _bran(state)
    assert bran["follow_mode"] == "waiting_here"
    assert bran["companion_role_state"] == "waiting"
    assert bran["location_id"] == "loc_tavern"


def test_waiting_companion_does_not_follow_player_location_sync():
    state = _state_with_bran_companion()
    maybe_apply_companion_command(
        state,
        player_input="Bran, stay here.",
        tick=1,
    )

    state["player_state"]["location_id"] = "loc_road"
    state["location_id"] = "loc_road"

    sync_active_companions_to_player_location(
        state,
        location_id="loc_road",
        tick=2,
        reason="travel",
    )

    bran = _bran(state)
    assert bran["follow_mode"] == "waiting_here"
    assert bran["location_id"] == "loc_tavern"


def test_follow_command_sets_following_player():
    state = _state_with_bran_companion()
    maybe_apply_companion_command(
        state,
        player_input="Bran, stay here.",
        tick=1,
    )

    state["player_state"]["location_id"] = "loc_road"
    state["location_id"] = "loc_road"

    result = maybe_apply_companion_command(
        state,
        player_input="Bran, follow me.",
        tick=3,
    )

    assert result["recognized"] is True
    assert result["accepted"] is True
    assert result["command"] == "follow"

    bran = _bran(state)
    assert bran["follow_mode"] == "following_player"
    assert bran["companion_role_state"] == "following"
    assert bran["location_id"] == "loc_road"


def test_impossible_command_is_rejected_without_mutation():
    state = _state_with_bran_companion()

    result = maybe_apply_companion_command(
        state,
        player_input="Bran, teleport to the king.",
        tick=4,
    )

    assert result["recognized"] is True
    assert result["accepted"] is False
    assert result["rejection_reason"] == "impossible_command"

    bran = _bran(state)
    assert bran["follow_mode"] == "following_player"
    assert bran.get("companion_role_state", "") == ""
