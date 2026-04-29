from app.rpg.interactions.interaction_runtime import resolve_general_interaction


def _state():
    return {
        "location_id": "loc_tavern_road",
        "player_state": {
            "location_id": "loc_tavern_road",
            "inventory": {
                "items": [
                    {
                        "item_id": "item:wooden_sticks",
                        "definition_id": "def:wooden_stick",
                        "name": "wooden sticks",
                        "aliases": ["stick", "sticks"],
                        "quantity": 3,
                    },
                    {
                        "item_id": "item:cloth_scraps",
                        "definition_id": "def:cloth_scrap",
                        "name": "cloth scraps",
                        "aliases": ["cloth scrap", "scraps"],
                        "quantity": 3,
                    },
                    {
                        "item_id": "item:oil_flasks",
                        "definition_id": "def:oil_flask",
                        "name": "oil flasks",
                        "aliases": ["oil", "flask of oil"],
                        "quantity": 2,
                    },
                ],
                "equipment": {},
                "carry_capacity": 50.0,
            },
        },
        "scene_items": [],
        "scene_objects": [],
    }


def _item_by_def(state, definition_id):
    for item in state["player_state"]["inventory"]["items"]:
        if item.get("definition_id") == definition_id:
            return item
    return {}


def test_craft_torch_consumes_materials_and_creates_output():
    state = _state()

    result = resolve_general_interaction(
        state,
        player_input="I craft a torch.",
        tick=1,
    )

    crafting = result["crafting_result"]
    assert crafting["resolved"] is True
    assert crafting["changed_state"] is True
    assert crafting["reason"] == "recipe_crafted"
    assert crafting["recipe_id"] == "recipe:torch"

    assert _item_by_def(state, "def:torch")["quantity"] == 1
    assert _item_by_def(state, "def:wooden_stick")["quantity"] == 2
    assert _item_by_def(state, "def:cloth_scrap")["quantity"] == 2
    assert _item_by_def(state, "def:oil_flask")["quantity"] == 1


def test_craft_arrows_stacks_output():
    state = _state()

    result = resolve_general_interaction(
        state,
        player_input="I craft iron arrows.",
        tick=1,
    )

    crafting = result["crafting_result"]
    assert crafting["resolved"] is True
    assert crafting["reason"] == "recipe_crafted"
    assert crafting["recipe_id"] == "recipe:arrow_bundle"

    arrows = _item_by_def(state, "def:iron_arrow")
    assert arrows["quantity"] == 5


def test_crafting_missing_materials_fails_without_mutation():
    state = _state()

    resolve_general_interaction(
        state,
        player_input="I craft a torch.",
        tick=1,
    )
    resolve_general_interaction(
        state,
        player_input="I craft iron arrows.",
        tick=2,
    )
    result = resolve_general_interaction(
        state,
        player_input="I craft a torch.",
        tick=3,
    )

    crafting = result["crafting_result"]
    assert crafting["resolved"] is False
    assert crafting["changed_state"] is False
    assert crafting["reason"] == "missing_crafting_materials"

    assert _item_by_def(state, "def:torch")["quantity"] == 1
    assert not _item_by_def(state, "def:wooden_stick")
