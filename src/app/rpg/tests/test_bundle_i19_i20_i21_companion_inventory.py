from app.rpg.interactions.interaction_runtime import resolve_general_interaction


def _state():
    return {
        "location_id": "loc_tavern_road",
        "player_state": {
            "location_id": "loc_tavern_road",
            "inventory": {
                "items": [
                    {
                        "item_id": "item:hunting_bow",
                        "definition_id": "def:hunting_bow",
                        "name": "hunting bow",
                        "aliases": ["bow"],
                    },
                    {
                        "item_id": "item:padded_armor",
                        "definition_id": "def:padded_armor",
                        "name": "padded armor",
                        "aliases": ["armor"],
                    },
                    {
                        "item_id": "item:stolen_ring",
                        "definition_id": "def:stolen_ring",
                        "name": "stolen ring",
                        "aliases": ["ring"],
                    },
                ],
                "equipment": {},
                "carry_capacity": 50.0,
            },
            "party_state": {
                "max_size": 4,
                "companions": [
                    {
                        "npc_id": "npc:Bran",
                        "name": "Bran",
                        "role": "companion",
                        "status": "active",
                        "current_role": "Displaced tavern keeper",
                        "identity_arc": "revenge_after_losing_tavern",
                        "active_motivations": ["revenge"],
                        "loyalty": 35,
                        "inventory": {
                            "items": [],
                            "equipment": {},
                            "carry_capacity": 50.0,
                        },
                    },
                    {
                        "npc_id": "npc:Captain_Aldric",
                        "name": "Captain Aldric",
                        "role": "companion",
                        "status": "active",
                        "current_role": "Guard captain",
                        "personality": "lawful honorable protective",
                        "morality": "lawful guard justice",
                        "loyalty": 20,
                        "inventory": {
                            "items": [],
                            "equipment": {},
                            "carry_capacity": 50.0,
                        },
                    },
                ],
            },
        },
        "scene_items": [],
        "scene_objects": [],
    }


def _companion(state, npc_id):
    for companion in state["player_state"]["party_state"]["companions"]:
        if companion["npc_id"] == npc_id:
            return companion
    return {}


def _player_item_by_def(state, definition_id):
    for item in state["player_state"]["inventory"]["items"]:
        if item.get("definition_id") == definition_id:
            return item
    return {}


def _companion_item_by_def(state, npc_id, definition_id):
    companion = _companion(state, npc_id)
    for item in companion.get("inventory", {}).get("items", []):
        if item.get("definition_id") == definition_id:
            return item
    return {}


def test_give_weapon_to_bran_auto_equips_main_hand():
    state = _state()

    result = resolve_general_interaction(
        state,
        player_input="I give the hunting bow to Bran.",
        tick=1,
    )

    inventory = result["inventory_result"]
    acceptance = result["companion_item_acceptance_result"]
    auto_equip = result["companion_auto_equip_result"]

    assert inventory["resolved"] is True
    assert inventory["reason"] == "item_given_to_npc"
    assert acceptance["accepted"] is True
    assert auto_equip["equipped"] is True
    assert auto_equip["slot"] == "main_hand"

    bran = _companion(state, "npc:Bran")
    assert bran["inventory"]["equipment"]["main_hand"] == "item:hunting_bow"
    assert _companion_item_by_def(state, "npc:Bran", "def:hunting_bow")
    assert not _player_item_by_def(state, "def:hunting_bow")


def test_give_armor_to_bran_auto_equips_body():
    state = _state()

    resolve_general_interaction(
        state,
        player_input="I give the padded armor to Bran.",
        tick=1,
    )

    bran = _companion(state, "npc:Bran")
    assert bran["inventory"]["equipment"]["body"] == "item:padded_armor"
    assert _companion_item_by_def(state, "npc:Bran", "def:padded_armor")


def test_lawful_guard_refuses_stolen_ring_and_player_keeps_it():
    state = _state()

    result = resolve_general_interaction(
        state,
        player_input="I give the stolen ring to Captain Aldric.",
        tick=1,
    )

    inventory = result["inventory_result"]
    acceptance = result["companion_item_acceptance_result"]

    assert inventory["resolved"] is False
    assert inventory["changed_state"] is False
    assert inventory["reason"] == "companion_refused_item"
    assert acceptance["accepted"] is False
    assert acceptance["reason"] == "morality_refuses_stolen_goods"

    assert _player_item_by_def(state, "def:stolen_ring")
    assert not _companion_item_by_def(state, "npc:Captain_Aldric", "def:stolen_ring")
