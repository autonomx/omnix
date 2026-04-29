from app.rpg.interactions.interaction_runtime import resolve_general_interaction


def _state():
    return {
        "location_id": "loc_tavern_road",
        "player_state": {
            "location_id": "loc_tavern_road",
            "inventory": {
                "items": [
                    {
                        "item_id": "item:small_knife",
                        "name": "small knife",
                        "aliases": ["knife"],
                        "kind": "weapon",
                        "slot": "main_hand",
                    }
                ],
                "equipment": {},
            },
            "party_state": {
                "companions": [
                    {
                        "npc_id": "npc:Bran",
                        "name": "Bran",
                        "status": "active",
                        "location_id": "loc_tavern_road",
                    }
                ]
            },
        },
        "scene_items": [
            {
                "item_id": "item:rusty_key",
                "name": "rusty key",
                "aliases": ["key"],
                "location_id": "loc_tavern_road",
                "kind": "key",
            },
            {
                "item_id": "item:rusty_dagger",
                "name": "rusty dagger",
                "aliases": ["dagger"],
                "location_id": "loc_tavern_road",
                "kind": "weapon",
                "slot": "main_hand",
            },
        ],
        "scene_objects": [],
    }


def _player_items(state):
    return [
        item["item_id"]
        for item in state["player_state"]["inventory"]["items"]
    ]


def _scene_items(state):
    return [
        item["item_id"]
        for item in state["scene_items"]
    ]


def _bran_items(state):
    companion = state["player_state"]["party_state"]["companions"][0]
    return [
        item["item_id"]
        for item in companion.get("inventory", {}).get("items", [])
    ]


def test_take_item_moves_scene_item_to_inventory():
    state = _state()

    result = resolve_general_interaction(
        state,
        player_input="I pick up the rusty key.",
        tick=1,
    )

    inventory = result["inventory_result"]
    assert inventory["resolved"] is True
    assert inventory["changed_state"] is True
    assert inventory["reason"] == "item_added_to_inventory"

    assert "item:rusty_key" in _player_items(state)
    assert "item:rusty_key" not in _scene_items(state)


def test_drop_item_moves_inventory_item_to_scene():
    state = _state()

    resolve_general_interaction(
        state,
        player_input="I pick up the rusty key.",
        tick=1,
    )
    result = resolve_general_interaction(
        state,
        player_input="I drop the rusty key.",
        tick=2,
    )

    inventory = result["inventory_result"]
    assert inventory["reason"] == "item_dropped_to_location"

    assert "item:rusty_key" not in _player_items(state)
    assert "item:rusty_key" in _scene_items(state)


def test_equip_item_sets_equipment_slot():
    state = _state()

    resolve_general_interaction(
        state,
        player_input="I pick up the rusty dagger.",
        tick=1,
    )
    result = resolve_general_interaction(
        state,
        player_input="I equip the rusty dagger.",
        tick=2,
    )

    inventory = result["inventory_result"]
    assert inventory["reason"] == "item_equipped"
    assert inventory["slot"] == "main_hand"
    assert state["player_state"]["inventory"]["equipment"]["main_hand"] == "item:rusty_dagger"


def test_give_item_to_companion_moves_item():
    state = _state()

    result = resolve_general_interaction(
        state,
        player_input="I give the small knife to Bran.",
        tick=1,
    )

    inventory = result["inventory_result"]
    assert inventory["reason"] == "item_given_to_npc"
    assert inventory["recipient_id"] == "npc:Bran"

    assert "item:small_knife" not in _player_items(state)
    assert "item:small_knife" in _bran_items(state)


def test_take_missing_item_fails_without_mutation():
    state = _state()

    result = resolve_general_interaction(
        state,
        player_input="I pick up the golden crown.",
        tick=1,
    )

    assert result["handled"] is False
    assert result["interaction_result"]["reason"] == "target_not_found"
    assert "item:golden_crown" not in _player_items(state)
