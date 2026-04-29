from app.rpg.party.companion_presence import (
    build_party_aware_turn_context,
    project_active_companions_into_presence,
    sync_active_companions_to_player_location,
)
from app.rpg.party.companion_turns import maybe_build_direct_companion_turn_response


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


def test_active_companion_projects_into_presence_state():
    state = _state_with_bran_companion()

    result = project_active_companions_into_presence(
        state,
        location_id="loc_tavern",
        tick=1,
        reason="test",
    )

    assert result["projected"] is True
    projected = result["projected_companions"]
    assert projected[0]["npc_id"] == "npc:Bran"
    assert projected[0]["presence_kind"] == "party_companion"

    present = state["present_npc_state"]["by_location"]["loc_tavern"]["present_npcs"]
    assert any(item["npc_id"] == "npc:Bran" for item in present)


def test_following_companion_moves_to_player_location():
    state = _state_with_bran_companion()
    state["player_state"]["location_id"] = "loc_road"
    state["location_id"] = "loc_road"

    result = sync_active_companions_to_player_location(
        state,
        location_id="loc_road",
        tick=2,
        reason="travel",
    )

    assert result["changed"][0]["npc_id"] == "npc:Bran"
    bran = state["player_state"]["party_state"]["companions"][0]
    assert bran["location_id"] == "loc_road"


def test_party_aware_context_detects_direct_bran_address():
    state = _state_with_bran_companion()

    context = build_party_aware_turn_context(
        state,
        player_input="Bran, what do you think?",
        tick=3,
    )

    addressed = context["addressed_companion"]
    assert addressed["matched"] is True
    assert addressed["npc_id"] == "npc:Bran"


def test_direct_companion_response_uses_revenge_arc():
    state = _state_with_bran_companion()

    response = maybe_build_direct_companion_turn_response(
        state,
        player_input="Bran, what do you think we should do next?",
        tick=4,
    )

    assert response["matched"] is True
    assert response["npc_id"] == "npc:Bran"
    assert response["npc_response_beat"]["speaker_id"] == "npc:Bran"
    assert "bandits" in response["line"].lower()
