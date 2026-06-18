from __future__ import annotations

from typing import Any

from app.rpg.session import loadout
from app.rpg.session.item_use import use_inventory_item


def _state() -> dict[str, Any]:
    return {
        "current_turn": 0,
        "turn_count": 0,
        "world": {"time": "Day 1 • 08:00"},
        "player": {
            "resources": {
                "hp": {"current": 20, "max": 50},
                "mana": {"current": 5, "max": 20},
                "stamina": {"current": 10, "max": 30},
            },
            "inventory": [],
            "equipment": [],
        },
        "timeline": [],
        "journal": {"entries": []},
    }


def _session() -> dict[str, Any]:
    state = _state()
    state["session_id"] = "rpg_item_use_test"
    state["player"]["name"] = "Test Hero"
    state["player"]["inventory"] = [
        {
            "item_id": "field_medkit",
            "id": "field_medkit",
            "name": "Field Medkit",
            "quantity": 1,
            "item_type": "consumable",
            "type": "consumable",
            "use_effect_ops": [
                {"op": "restore_resource", "resource": "hp", "amount": 15},
                {"op": "award_xp", "amount": 999},
            ],
        }
    ]
    return {
        "manifest": {"id": "rpg_item_use_test", "session_id": "rpg_item_use_test", "title": "Test", "updated_at": "before"},
        "state": state,
    }


def test_item_use_resolves_validated_effect_ops_and_ignores_unknown_mechanics() -> None:
    state = _state()
    player = state["player"]
    inventory = [
        {
            "item_id": "field_medkit",
            "name": "Field Medkit",
            "quantity": 1,
            "item_type": "consumable",
            "use_effect_ops": [
                {"op": "restore_resource", "resource": "hp", "amount": 15},
                {"op": "award_xp", "amount": 999},
            ],
        }
    ]

    result = use_inventory_item(state, player, inventory, 0, inventory[0])

    assert result["ok"] is True
    assert player["resources"]["hp"] == {"current": 35, "max": 50}
    assert inventory == []
    assert result["effects"] == [{"op": "restore_resource", "resource": "hp", "amount": 15, "current": 35, "max": 50}]
    assert result["repairs"] == ["ignored_unsupported_item_effect_op:award_xp"]
    assert result["trace"]["event"] == "item_used"
    assert result["trace"]["consumed"] is True
    assert result["trace"]["mechanics_source"] == "explicit_item_use_effect_ops_v1"


def test_legacy_torch_use_adds_scene_status_without_consuming() -> None:
    state = _state()
    player = state["player"]
    inventory = [{"item_id": "torch", "name": "Torch", "quantity": 1, "item_type": "tool"}]

    result = use_inventory_item(state, player, inventory, 0, inventory[0])

    assert result["ok"] is True
    assert inventory[0]["quantity"] == 1
    assert state["scene_state"]["statuses"][0]["status"] == "lit_torch"
    assert result["effects"] == [{"op": "add_scene_status", "status": "lit_torch", "dimension": "environment"}]
    assert result["trace"]["mechanics_source"] == "legacy_item_use_fallback_v1"


def test_legacy_document_use_adds_dialogue_affordance_without_consuming() -> None:
    state = _state()
    player = state["player"]
    inventory = [{"item_id": "journal", "name": "Journal", "quantity": 1, "item_type": "quest_item", "protected": True}]

    result = use_inventory_item(state, player, inventory, 0, inventory[0])

    assert result["ok"] is True
    assert inventory[0]["quantity"] == 1
    affordance = state["narrative_affordances"]["dialogue"][0]
    assert affordance["tag"] == "ask_about_written_clue"
    assert affordance["source"] == "Journal"
    assert result["effects"] == [{"op": "add_affordance", "bucket": "dialogue", "tag": "ask_about_written_clue", "dimension": "narrative"}]


def test_loadout_use_writes_item_use_trace_and_event_effects(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []
    monkeypatch.setattr(loadout, "load_session", lambda session_id: _session())
    monkeypatch.setattr(loadout, "save_session", lambda session, *, compact=False: saved.append(session) or session)

    result = loadout.apply_loadout_action("rpg_item_use_test", loadout.RpgLoadoutActionRequest(action="use", item_name="Field Medkit"))

    assert result["ok"] is True
    state = saved[0]["state"]
    assert state["player"]["resources"]["hp"] == {"current": 35, "max": 50}
    assert state["player"]["inventory"] == []
    assert state["timeline"][0]["kind"] == "item"
    assert state["timeline"][0]["effects"] == [{"op": "restore_resource", "resource": "hp", "amount": 15, "current": 35, "max": 50}]
    trace = state["mechanics"]["item_use_traces"][0]
    assert trace["event"] == "item_used"
    assert trace["source_item_id"] == "field_medkit"
    assert trace["repairs"] == ["ignored_unsupported_item_effect_op:award_xp"]
    assert state["mechanics"]["item_traces"][0] == trace
    assert result["mechanics_trace"] == trace
