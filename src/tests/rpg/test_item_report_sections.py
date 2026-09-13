from __future__ import annotations

from app.rpg.session.item_report_sections import build_item_report_section, record_item_report_section


def _state() -> dict[str, object]:
    return {
        "player": {
            "inventory": [
                {
                    "item_id": "ration",
                    "name": "Trail ration",
                    "item_type": "consumable",
                    "quantity": 2,
                    "value": {"copper": 4},
                },
                {
                    "item_id": "iron",
                    "name": "Iron scrap",
                    "item_type": "crafting_material",
                    "material_id": "iron",
                    "quantity": 3,
                    "stackable": True,
                },
                {
                    "item_id": "sealed_note",
                    "name": "Sealed note",
                    "item_type": "note",
                    "quantity": 1,
                    "protected": True,
                    "tags": ["letter"],
                },
            ]
        },
        "crafting": {"known_recipes": ["torch_basic"]},
        "mechanics": {
            "item_use_traces": [{"event": "item_used"}],
            "salvage_traces": [{"event": "item_salvaged"}],
            "crafting_traces": [{"event": "item_crafted"}],
            "pickup_traces": [{"event": "scene_item_picked_up"}],
            "market_traces": [{"event": "market_quote_built"}],
            "signal_traces": [{"event": "item_signal_applied"}],
        },
    }


def test_item_report_section_combines_metrics_actions_and_coverage() -> None:
    section = build_item_report_section(_state())

    assert section["ok"] is True
    assert section["title"] == "Item System Coverage"
    assert section["summary"]["item_count"] == 3
    assert section["summary"]["total_quantity"] == 6
    assert section["summary"]["known_recipe_count"] == 1
    assert section["summary"]["trace_total"] == 6
    assert section["inventory"]["by_type"]["crafting_material"] == 3
    assert section["inventory"]["material_ids"] == ["iron"]
    assert "inventory" in section["coverage"]["present"]
    assert "materials" in section["coverage"]["present"]
    assert "modifications" in section["coverage"]["missing"]
    assert section["trace"]["event"] == "item_report_section_built"


def test_item_report_section_counts_enabled_and_disabled_actions() -> None:
    section = build_item_report_section(_state())
    actions = section["actions"]

    assert actions["enabled_by_action"]["inspect"] == 3
    assert actions["enabled_by_action"]["use"] >= 2
    assert actions["enabled_by_action"]["sell"] == 1
    assert actions["disabled_reasons"]["protected_item"] >= 1
    assert actions["recipe_summary"]["known_or_available_count"] == 1
    assert actions["recipe_summary"]["craftable_count"] == 0
    assert actions["recipe_summary"]["blocked_count"] == 1


def test_record_item_report_section_prepends_without_inventory_mutation() -> None:
    state = _state()
    state["mechanics"]["item_report_sections"] = [{"old": True}]

    section = record_item_report_section(state)

    assert state["player"]["inventory"][0]["quantity"] == 2
    assert state["mechanics"]["item_report_sections"][0] == section
    assert state["mechanics"]["item_report_sections"][1] == {"old": True}
    assert section["mechanics_source"] == "engine_item_report_section_v1"
