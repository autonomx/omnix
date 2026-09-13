from __future__ import annotations

from typing import Any

from app.rpg.session import loadout
from app.rpg.session.item_use import use_inventory_item


def _state() -> dict[str, Any]:
    return {
        "current_turn": 0,
        "turn_count": 0,
        "world": {"time": "Day 1 • 08:00"},
        "player": {"resources": {}, "inventory": [], "equipment": []},
        "timeline": [],
        "journal": {"entries": []},
    }


def test_map_item_grants_travel_affordance_without_consuming() -> None:
    state = _state()
    player = state["player"]
    inventory = [{"item_id": "harbor_map", "name": "Harbor Map", "quantity": 1, "item_type": "document"}]

    result = use_inventory_item(state, player, inventory, 0, inventory[0])

    assert result["ok"] is True
    assert inventory[0]["quantity"] == 1
    assert state["narrative_affordances"]["travel"][0]["tag"] == "study_map_route"
    assert result["effects"] == [{"op": "add_affordance", "bucket": "travel", "tag": "study_map_route", "dimension": "access"}]


def test_blueprint_item_grants_crafting_affordance_without_consuming() -> None:
    state = _state()
    player = state["player"]
    inventory = [{"item_id": "workshop_blueprint", "name": "Workshop Blueprint", "quantity": 1, "item_type": "document"}]

    result = use_inventory_item(state, player, inventory, 0, inventory[0])

    assert result["ok"] is True
    assert inventory[0]["quantity"] == 1
    assert state["narrative_affordances"]["crafting"][0]["tag"] == "study_blueprint_recipe_clue"
    assert result["effects"] == [{"op": "add_affordance", "bucket": "crafting", "tag": "study_blueprint_recipe_clue", "dimension": "knowledge"}]


def test_access_document_grants_access_affordance_without_consuming() -> None:
    state = _state()
    player = state["player"]
    inventory = [{"item_id": "court_seal", "name": "Court Seal", "quantity": 1, "item_type": "key"}]

    result = use_inventory_item(state, player, inventory, 0, inventory[0])

    assert result["ok"] is True
    assert inventory[0]["quantity"] == 1
    assert state["narrative_affordances"]["access"][0]["tag"] == "present_authorizing_document"
    assert result["effects"] == [{"op": "add_affordance", "bucket": "access", "tag": "present_authorizing_document", "dimension": "access"}]


def test_loadout_use_knowledge_item_writes_affordance_trace_and_event(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []
    session = {
        "manifest": {"id": "rpg_knowledge_test", "session_id": "rpg_knowledge_test", "title": "Test", "updated_at": "before"},
        "state": {
            "session_id": "rpg_knowledge_test",
            "current_turn": 0,
            "turn_count": 0,
            "world": {"time": "Day 1 • 08:00"},
            "player": {
                "name": "Test Hero",
                "resources": {},
                "inventory": [{"id": "harbor_map", "name": "Harbor Map", "quantity": 1, "item_type": "document"}],
                "equipment": [],
            },
            "timeline": [],
            "journal": {"entries": []},
        },
    }
    monkeypatch.setattr(loadout, "load_session", lambda session_id: session)
    monkeypatch.setattr(loadout, "save_session", lambda updated, *, compact=False: saved.append(updated) or updated)

    result = loadout.apply_loadout_action("rpg_knowledge_test", loadout.RpgLoadoutActionRequest(action="use", item_name="Harbor Map"))

    assert result["ok"] is True
    state = saved[0]["state"]
    assert state["timeline"][0]["kind"] == "item"
    assert state["timeline"][0]["effects"] == [{"op": "add_affordance", "bucket": "travel", "tag": "study_map_route", "dimension": "access"}]
    assert state["narrative_affordances"]["travel"][0]["source"] == "Harbor Map"
    trace = state["mechanics"]["item_use_traces"][0]
    assert trace["source_item_name"] == "Harbor Map"
    assert trace["effects"] == state["timeline"][0]["effects"]
    assert state["mechanics"]["item_traces"][0] == trace
