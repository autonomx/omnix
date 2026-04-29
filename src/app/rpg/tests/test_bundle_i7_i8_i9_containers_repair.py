from app.rpg.interactions.interaction_runtime import resolve_general_interaction
from app.rpg.interactions.item_model import normalize_item_instance
from app.rpg.session.runtime import (
    _apply_visible_interaction_reason_to_resolved_result,
    _interaction_visible_result_reason,
    _replace_stale_visible_result_text,
    _patch_visible_interaction_reason_into_payload_text,
)


def _state():
    return {
        "location_id": "loc_tavern_road",
        "player_state": {
            "location_id": "loc_tavern_road",
            "inventory": {
                "items": [
                    {
                        "item_id": "item:iron_arrow_stack_a",
                        "definition_id": "def:iron_arrow",
                        "name": "iron arrows",
                        "aliases": ["arrows", "iron arrow"],
                        "quantity": 15,
                    },
                    {
                        "item_id": "item:leather_satchel",
                        "definition_id": "def:leather_satchel",
                        "name": "leather satchel",
                        "aliases": ["satchel", "bag"],
                    },
                    {
                        "item_id": "item:rusty_dagger",
                        "definition_id": "def:rusty_dagger",
                        "name": "rusty dagger",
                        "aliases": ["dagger"],
                        "condition": {
                            "durability": 0.55,
                            "max_durability": 1.0,
                        },
                    },
                    {
                        "item_id": "item:whetstone",
                        "definition_id": "def:whetstone",
                        "name": "whetstone",
                    },
                    {
                        "item_id": "item:torn_cloak",
                        "definition_id": "def:torn_cloak",
                        "name": "torn cloak",
                        "aliases": ["cloak"],
                        "condition": {
                            "durability": 0.35,
                            "max_durability": 1.0,
                        },
                    },
                    {
                        "item_id": "item:cloth_scraps",
                        "definition_id": "def:cloth_scrap",
                        "name": "cloth scraps",
                        "aliases": ["cloth scrap", "scraps"],
                        "quantity": 4,
                    },
                ],
                "equipment": {},
                "carry_capacity": 50.0,
            },
        },
        "scene_items": [],
        "scene_objects": [],
    }


def _items(state):
    return state["player_state"]["inventory"]["items"]


def _item(state, item_id):
    for item in _items(state):
        if item.get("item_id") == item_id:
            return item
    return {}


def test_put_items_into_container():
    state = _state()

    result = resolve_general_interaction(
        state,
        player_input="I put 15 iron arrows into the leather satchel.",
        tick=1,
    )

    container = result["container_result"]
    assert container["resolved"] is True
    assert container["changed_state"] is True
    assert container["reason"] == "item_added_to_container"

    assert not _item(state, "item:iron_arrow_stack_a")

    satchel = _item(state, "item:leather_satchel")
    contents = satchel["container"]["items"]
    assert contents[0]["definition_id"] == "def:iron_arrow"
    assert contents[0]["quantity"] == 15


def test_repair_weapon_with_tool():
    state = _state()

    result = resolve_general_interaction(
        state,
        player_input="I repair the rusty dagger with the whetstone.",
        tick=1,
    )

    repair = result["repair_result"]
    assert repair["resolved"] is True
    assert repair["reason"] == "item_repaired_with_tool"
    assert repair["condition_before"] == 0.55
    assert repair["condition_after"] == 0.75

    dagger = _item(state, "item:rusty_dagger")
    assert dagger["condition"]["durability"] == 0.75


def test_repair_cloak_with_material_consumes_scraps():
    state = _state()

    result = resolve_general_interaction(
        state,
        player_input="I repair the torn cloak with 2 cloth scraps.",
        tick=1,
    )

    repair = result["repair_result"]
    assert repair["resolved"] is True
    assert repair["reason"] == "item_repaired_with_material"
    assert repair["condition_before"] == 0.35
    assert repair["condition_after"] == 0.65
    assert repair["materials_consumed"][0]["quantity"] == 2

    cloak = _item(state, "item:torn_cloak")
    scraps = _item(state, "item:cloth_scraps")

    assert cloak["condition"]["durability"] == 0.65
    assert scraps["quantity"] == 2


def test_wrong_repair_material_fails():
    state = _state()

    result = resolve_general_interaction(
        state,
        player_input="I repair the rusty dagger with 2 cloth scraps.",
        tick=1,
    )

    repair = result["repair_result"]
    assert repair["resolved"] is False
    assert repair["changed_state"] is False
    assert repair["reason"] == "repair_material_not_applicable"

    dagger = _item(state, "item:rusty_dagger")
    scraps = _item(state, "item:cloth_scraps")

    assert dagger["condition"]["durability"] == 0.55
    assert scraps["quantity"] == 4


def test_repair_metadata_survives_item_normalization():
    whetstone = normalize_item_instance({
        "item_id": "item:whetstone",
        "definition_id": "def:whetstone",
    })
    assert whetstone["repair"]["tool"] is True
    assert "blade" in whetstone["repair"]["target_tags"]

    scraps = normalize_item_instance({
        "item_id": "item:cloth_scraps",
        "definition_id": "def:cloth_scrap",
        "quantity": 4,
    })
    assert scraps["repair"]["material"] is True
    assert scraps["repair"]["default_quantity"] == 2


def test_visible_interaction_reason_overrides_stale_result():
    general = {
        "interaction_result": {
            "resolved": True,
            "changed_state": True,
            "reason": "item_added_to_container",
            "container_result": {
                "resolved": True,
                "changed_state": True,
                "reason": "item_added_to_container",
            },
        },
        "container_result": {
            "resolved": True,
            "changed_state": True,
            "reason": "item_added_to_container",
        },
    }

    assert _interaction_visible_result_reason(general) == "item_added_to_container"

    resolved = {
        "result": "unknown_item",
        "action": "Result: unknown_item",
    }
    patched = _apply_visible_interaction_reason_to_resolved_result(
        resolved,
        general_interaction_result=general,
    )

    assert patched["visible_interaction_reason"] == "item_added_to_container"
    assert patched["result"] == "item_added_to_container"
    assert patched["action"] == "Result: item_added_to_container"


def test_replace_stale_visible_result_text_in_narration():
    text = (
        "The action resolves against the current situation.\n\n"
        "Action: You put 15 iron arrows into the leather satchel.\n\n"
        "Result: unknown_item"
    )

    patched = _replace_stale_visible_result_text(
        text,
        visible_reason="item_added_to_container",
    )

    assert "Result: unknown_item" not in patched
    assert "Result: item_added_to_container" in patched


def test_patch_visible_interaction_reason_into_payload_text():
    payload = {
        "narration_preview": "Action: Something.\n\nResult: unknown_item",
        "final_narration": "Action: Something.\n\nResult: item_not_found",
        "raw_payload_narration": "Action: Something.\n\nResult: unknown",
    }

    patched = _patch_visible_interaction_reason_into_payload_text(
        payload,
        visible_reason="item_repaired_with_tool",
    )

    assert "Result: item_repaired_with_tool" in patched["narration_preview"]
    assert "Result: item_repaired_with_tool" in patched["final_narration"]
    assert "Result: item_repaired_with_tool" in patched["raw_payload_narration"]