from app.rpg.session.recipe_discovery import (
    apply_recipe_discovery,
    discover_recipes,
    known_recipe_ids,
    recipe_ids_from_item,
)


def test_known_recipe_ids_reads_state_and_player_shapes():
    state = {
        "crafting": {"known_recipes": [{"recipe_id": "torch"}]},
        "known_recipes": ["missing_recipe"],
    }
    player = {"known_recipes": [{"id": "crude_blade"}]}

    assert known_recipe_ids(state, player) == ["crude_blade", "torch"]


def test_recipe_ids_from_item_uses_explicit_catalog_recipe_ids():
    item = {
        "name": "Field Manual",
        "item_type": "document",
        "teaches_recipes": ["torch", "unknown_recipe"],
    }

    discoveries = recipe_ids_from_item(item)

    assert [entry["recipe_id"] for entry in discoveries] == ["torch"]
    assert discoveries[0]["source"] == "inventory_item"
    assert discoveries[0]["detail"] == "Field Manual"


def test_discover_recipes_uses_inventory_hints_without_mutating_state():
    state = {
        "player": {
            "inventory": [
                {"name": "Campfire Light Notes", "item_type": "document", "tags": ["campfire"]},
            ]
        }
    }

    result = discover_recipes(state)

    assert result["ok"] is True
    assert [entry["recipe_id"] for entry in result["discovered"]] == ["torch"]
    assert state.get("crafting") is None
    assert result["trace"]["event"] == "recipe_discovery_checked"


def test_apply_recipe_discovery_persists_sorted_known_recipes_and_trace():
    state = {
        "crafting": {"known_recipes": [{"recipe_id": "torch", "source": "existing"}]},
        "player": {
            "inventory": [
                {"name": "Forge Edge Notes", "item_type": "document", "tags": ["forge", "edge"]},
            ]
        },
    }

    result = apply_recipe_discovery(state)

    assert result["known_before"] == ["torch"]
    assert result["known_after"] == ["crude_blade", "torch"]
    assert [entry["recipe_id"] for entry in state["crafting"]["known_recipes"]] == ["crude_blade", "torch"]
    trace = state["crafting"]["recipe_discovery_traces"][0]
    assert trace["mechanics_source"] == "engine_recipe_discovery_v1"
    assert trace["known_after"] == ["crude_blade", "torch"]


def test_affordance_hints_can_discover_recipe():
    state = {
        "narrative_affordances": {
            "crafting": [
                {"tag": "study_blueprint_recipe_clue", "dimension": "knowledge"},
            ]
        },
        "player": {"inventory": []},
    }

    result = apply_recipe_discovery(state)

    assert result["known_after"] == ["crude_blade"]
    assert result["trace"]["discovered"][0]["source"] == "affordance:crafting"
