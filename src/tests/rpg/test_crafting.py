from __future__ import annotations

from typing import Any

from app.rpg.session import loadout
from app.rpg.session.crafting import craft_from_inventory, preview_craft


def _materials() -> list[dict[str, Any]]:
    return [
        {
            "item_id": "wood",
            "id": "wood",
            "name": "Wood scrap",
            "quantity": 1,
            "item_type": "crafting_material",
            "type": "crafting_material",
            "material_id": "wood",
            "material_role": "wood",
            "properties": ["burnable", "organic"],
            "stackable": True,
        },
        {
            "item_id": "cloth",
            "id": "cloth",
            "name": "Cloth scrap",
            "quantity": 1,
            "item_type": "crafting_material",
            "type": "crafting_material",
            "material_id": "cloth",
            "material_role": "cloth",
            "properties": ["flexible", "burnable", "binding"],
            "stackable": True,
        },
        {
            "item_id": "lamp_oil",
            "id": "lamp_oil",
            "name": "Lamp oil",
            "quantity": 1,
            "item_type": "crafting_material",
            "type": "crafting_material",
            "material_id": "lamp_oil",
            "material_role": "fuel",
            "properties": ["burnable"],
            "stackable": True,
        },
    ]


def _session() -> dict[str, Any]:
    return {
        "manifest": {"id": "rpg_test", "session_id": "rpg_test", "title": "Test", "updated_at": "before"},
        "state": {
            "session_id": "rpg_test",
            "current_turn": 0,
            "turn_count": 0,
            "world": {"time": "Day 1 • 08:00"},
            "summary": "Before",
            "player": {
                "name": "Test Hero",
                "resources": {
                    "hp": {"current": 50, "max": 100},
                    "stamina": {"current": 50, "max": 100},
                    "mana": {"current": 20, "max": 40},
                },
                "inventory": _materials(),
                "equipment": [],
            },
            "timeline": [],
            "journal": {"entries": []},
        },
    }


def test_preview_craft_rejects_wrong_station_and_missing_ingredients() -> None:
    wrong_station = preview_craft(_materials(), "torch", station="forge")
    missing = preview_craft(_materials()[:2], "torch", station="campfire")

    assert wrong_station["ok"] is False
    assert wrong_station["error"] == "wrong_station"
    assert wrong_station["required_station"] == "campfire"
    assert missing["ok"] is False
    assert missing["error"] == "missing_ingredients"
    assert missing["missing"] == [{"requirement": "lamp_oil", "quantity": 1}]
    assert missing["output_preview"]["item_id"] == "torch"


def test_craft_torch_consumes_materials_adds_output_and_writes_trace() -> None:
    inventory = _materials()

    result = craft_from_inventory(inventory, "torch", station="campfire")

    assert result["ok"] is True
    assert result["recipe_id"] == "torch"
    assert result["output"]["item_id"] == "torch"
    assert result["output"]["name"] == "Torch"
    assert result["output"]["instance_id"] == "inst_torch_crafted"
    assert {item.get("item_id") for item in inventory} == {"torch"}
    assert [entry["requirement"] for entry in result["consumed_items"]] == ["burnable material", "cloth", "lamp_oil"]
    trace = result["trace"]
    assert trace["event"] == "item_crafted"
    assert trace["recipe_id"] == "torch"
    assert trace["output"]["item_id"] == "torch"
    assert trace["mechanics_source"] == "engine_crafting_v1"


def test_loadout_craft_action_saves_inventory_event_and_trace(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []
    monkeypatch.setattr(loadout, "load_session", lambda session_id: _session())
    monkeypatch.setattr(loadout, "save_session", lambda session, *, compact=False: saved.append(session) or session)

    result = loadout.apply_loadout_action(
        "rpg_test",
        loadout.RpgLoadoutActionRequest(action="craft", recipe_id="torch", station="campfire"),
    )

    assert result["ok"] is True
    assert result["recipe_id"] == "torch"
    assert result["output"]["item_id"] == "torch"
    state = saved[0]["state"]
    assert state["turn_count"] == 1
    assert state["timeline"][0]["kind"] == "craft"
    assert state["timeline"][0]["title"] == "Crafted Torch"
    assert state["journal"]["entries"][0]["kind"] == "craft"
    assert {item.get("item_id") for item in state["player"]["inventory"]} == {"torch"}
    trace = state["mechanics"]["crafting_traces"][0]
    assert trace["event"] == "item_crafted"
    assert trace["recipe_id"] == "torch"
    assert state["mechanics"]["item_traces"][0] == trace


def test_loadout_craft_action_reports_missing_ingredients(monkeypatch) -> None:
    session = _session()
    session["state"]["player"]["inventory"] = _materials()[:2]
    monkeypatch.setattr(loadout, "load_session", lambda session_id: session)

    result = loadout.apply_loadout_action(
        "rpg_test",
        loadout.RpgLoadoutActionRequest(action="craft", recipe_id="torch", station="campfire"),
    )

    assert result["ok"] is False
    assert result["error"] == "missing_ingredients"
    assert result["recipe_id"] == "torch"
    assert result["missing"] == [{"requirement": "lamp_oil", "quantity": 1}]
