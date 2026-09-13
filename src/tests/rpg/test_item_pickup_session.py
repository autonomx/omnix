from __future__ import annotations

from app.rpg.session.item_pickup_session import apply_session_scene_item_pickup, available_scene_pickups_for_session


def test_available_scene_pickups_for_session_skips_depleted_nodes() -> None:
    state = {
        "scene_state": {
            "item_nodes": [
                {"id": "field_pack", "name": "Field Pack", "remaining": 2, "outputs": [{"item_id": "ration"}]},
                {"id": "empty_pack", "name": "Empty Pack", "remaining": 0},
            ]
        }
    }

    nodes = available_scene_pickups_for_session(state)

    assert nodes == [
        {
            "node_id": "field_pack",
            "name": "Field Pack",
            "remaining": 2,
            "has_explicit_outputs": True,
            "reward_table": "",
        }
    ]


def test_apply_session_scene_item_pickup_mutates_state_and_enriches_traces() -> None:
    state = {
        "current_turn": 7,
        "player": {"inventory": []},
        "scene_state": {
            "item_nodes": [
                {
                    "id": "field_pack",
                    "name": "Field Pack",
                    "remaining": 1,
                    "outputs": [
                        {
                            "item_id": "travel_ration",
                            "name": "Travel ration",
                            "item_type": "consumable",
                            "quantity": 2,
                            "stackable": True,
                        }
                    ],
                }
            ]
        },
    }

    result = apply_session_scene_item_pickup(state, "field_pack", source="autoplay_world_action")

    assert result["ok"] is True
    assert result["detail"] == "Collected 2 items from Field Pack."
    assert result["output_summary"] == [
        {"item_id": "travel_ration", "name": "Travel ration", "quantity": 2, "item_type": "consumable"}
    ]
    assert state["player"]["inventory"][0]["quantity"] == 2
    assert state["scene_state"]["item_nodes"][0]["depleted"] is True
    trace = result["mechanics_trace"]
    assert trace["event"] == "scene_item_picked_up"
    assert trace["session_event"] == "scene_item_pickup_session_applied"
    assert trace["session_source"] == "autoplay_world_action"
    assert trace["turn"] == 7
    assert trace["mechanics_source"] == "engine_item_pickup_session_v1"
    assert state["mechanics"]["pickup_traces"][0] == trace
    assert state["mechanics"]["item_traces"][0] == trace


def test_apply_session_scene_item_pickup_reports_missing_node_without_traces() -> None:
    state = {"player": {"inventory": []}, "scene_state": {"item_nodes": []}}

    result = apply_session_scene_item_pickup(state, "missing")

    assert result == {"ok": False, "error": "pickup_node_not_found", "node_id": "missing", "outputs": []}
    assert "mechanics" not in state
