from app.rpg.session.runtime import derive_action_candidates


def test_room_request_maps_to_rent_room():
    runtime_state = {"active_interactions": []}
    candidates = derive_action_candidates(
        {"active_interactions": []},
        "i ask bran for a room",
        runtime_state=runtime_state,
    )
    assert candidates
    assert candidates[0]["action_type"] == "rent_room"


def test_take_best_one_does_not_become_pickup_when_in_room_interaction():
    runtime_state = {
        "active_interactions": [
            {
                "id": "interaction:room",
                "action_type": "rent_room",
                "subtype": "inn_room_rental",
                "participants": ["player", "bran"],
            }
        ]
    }
    candidates = derive_action_candidates(
        {"active_interactions": runtime_state["active_interactions"]},
        "ill take the best one",
        runtime_state=runtime_state,
    )
    assert candidates
    assert candidates[0]["action_type"] == "rent_room"
    assert candidates[0]["tier"] == "best"
