from __future__ import annotations

from typing import Any

from app.rpg.session.recipe_discovery_session import apply_recipe_discovery_for_session


def _state() -> dict[str, Any]:
    return {
        "current_turn": 7,
        "player": {
            "inventory": [
                {
                    "item_id": "note_torch",
                    "name": "Field Note",
                    "item_type": "knowledge",
                    "teaches_recipes": ["torch"],
                }
            ]
        },
    }


def test_recipe_discovery_session_bridge_persists_known_recipe_and_mechanics_trace() -> None:
    state = _state()

    result = apply_recipe_discovery_for_session(state, source="use_item")

    assert result["ok"] is True
    assert result["known_before"] == []
    assert result["known_after"] == ["torch"]
    assert result["discovered"][0]["recipe_id"] == "torch"
    assert result["recorded"] is True
    assert state["crafting"]["known_recipes"] == [
        {"recipe_id": "torch", "name": "Torch", "source": "inventory_item", "detail": "Field Note", "station": "camp"}
    ]
    trace = state["mechanics"]["recipe_discovery_traces"][0]
    assert trace["event"] == "recipe_discovery_session_checked"
    assert trace["source"] == "use_item"
    assert trace["turn"] == 7
    assert trace["known_after"] == ["torch"]
    assert state["mechanics"]["item_traces"][0] == trace


def test_recipe_discovery_session_bridge_skips_empty_mechanics_trace_by_default() -> None:
    state = {"player": {"inventory": [{"item_id": "rope", "name": "Rope"}]}}

    result = apply_recipe_discovery_for_session(state, source="inspect")

    assert result["ok"] is True
    assert result["known_after"] == []
    assert result["discovered"] == []
    assert result["recorded"] is False
    assert "mechanics" not in state
    assert state["crafting"]["known_recipes"] == []


def test_recipe_discovery_session_bridge_can_record_empty_diagnostics() -> None:
    state = {"turn_count": 3, "player": {"inventory": []}}

    result = apply_recipe_discovery_for_session(state, source="diagnostic", record_empty=True)

    assert result["recorded"] is True
    trace = state["mechanics"]["recipe_discovery_traces"][0]
    assert trace["source"] == "diagnostic"
    assert trace["turn"] == 3
    assert trace["discovered"] == []
