from __future__ import annotations

from app.rpg.session.item_metrics import build_item_metrics_snapshot, record_item_metrics_snapshot


def test_item_metrics_summarizes_inventory_types_and_materials() -> None:
    state = {
        "player": {
            "inventory": [
                {"item_id": "iron", "name": "Iron scrap", "item_type": "crafting_material", "material_id": "iron", "quantity": 3, "stackable": True},
                {"item_id": "sealed_record", "name": "Sealed Record", "item_type": "relic", "quantity": 1, "protected": True},
            ]
        }
    }

    snapshot = build_item_metrics_snapshot(state)

    assert snapshot["ok"] is True
    assert snapshot["inventory"]["item_count"] == 2
    assert snapshot["inventory"]["total_quantity"] == 4
    assert snapshot["inventory"]["by_type"]["crafting_material"] == 3
    assert snapshot["inventory"]["material_ids"] == ["iron"]
    assert snapshot["inventory"]["protected_count"] == 1
    assert snapshot["feature_flags"]["has_materials"] is True


def test_item_metrics_reads_known_recipe_shapes() -> None:
    list_state = {"crafting": {"known_recipes": ["torch_basic", "bandage_basic"]}}
    dict_state = {"crafting": {"known_recipes": {"torch_basic": {"source": "note"}}}}

    assert build_item_metrics_snapshot(list_state)["known_recipes"] == ["bandage_basic", "torch_basic"]
    assert build_item_metrics_snapshot(dict_state)["known_recipes"] == ["torch_basic"]


def test_item_metrics_summarizes_mechanics_trace_presence() -> None:
    state = {
        "mechanics": {
            "item_use_traces": [{"event": "item_used"}],
            "salvage_traces": [{"event": "item_salvaged"}],
            "crafting_traces": [],
            "pickup_traces": [{"event": "scene_item_picked_up"}],
            "signal_traces": [{"event": "item_signal_applied"}],
        }
    }

    snapshot = build_item_metrics_snapshot(state)

    assert snapshot["traces"]["counts"]["item_used"] == 1
    assert snapshot["traces"]["counts"]["salvaged"] == 1
    assert snapshot["traces"]["counts"]["crafted"] == 0
    assert "picked_up" in snapshot["traces"]["present"]
    assert snapshot["feature_flags"]["has_item_use"] is True
    assert snapshot["feature_flags"]["has_scene_pickups"] is True
    assert snapshot["feature_flags"]["has_item_signals"] is True


def test_record_item_metrics_snapshot_prepends_snapshot_without_mutating_inventory() -> None:
    state = {
        "player": {"inventory": [{"item_id": "ration", "name": "Ration", "item_type": "consumable", "quantity": 2}]},
        "mechanics": {"item_metric_snapshots": [{"old": True}]},
    }

    snapshot = record_item_metrics_snapshot(state)

    assert state["player"]["inventory"][0]["quantity"] == 2
    assert state["mechanics"]["item_metric_snapshots"][0] == snapshot
    assert state["mechanics"]["item_metric_snapshots"][1] == {"old": True}
    assert snapshot["mechanics_source"] == "engine_item_metrics_v1"
