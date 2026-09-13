from __future__ import annotations

from app.rpg.session.item_state_audit import build_item_state_audit, record_item_state_audit


def test_item_state_audit_accepts_clean_item_state() -> None:
    state = {
        "player": {
            "currency": {"gold": 1, "silver": 2, "copper": 3},
            "inventory": [
                {"item_id": "explorer_coat", "name": "Explorer Coat", "item_type": "armor", "quantity": 1},
                {"material_id": "cloth", "name": "Cloth", "item_type": "crafting_material", "quantity": 2, "stackable": True},
            ],
            "equipment": {"body": "explorer_coat"},
        },
        "crafting": {"known_recipes": ["torch"]},
        "mechanics": {"item_traces": []},
    }

    audit = build_item_state_audit(state)

    assert audit["ok"] is True
    assert audit["severity"] == "ok"
    assert audit["issues"] == []
    assert audit["summary"]["inventory_items"] == 2
    assert audit["summary"]["currency_copper_total"] == 123
    assert audit["summary"]["known_recipes"] == ["torch"]


def test_item_state_audit_reports_invalid_item_state() -> None:
    state = {
        "player": {
            "currency": {"gold": 0, "silver": 0, "copper": -1},
            "inventory": [
                "Old Map",
                {"name": "Bent Token", "quantity": -2},
            ],
            "equipment": {"hand": "missing_tool"},
        },
        "crafting": {"known_recipes": ["missing_recipe"]},
        "mechanics": {"item_traces": "bad"},
    }

    audit = build_item_state_audit(state)

    assert audit["ok"] is False
    assert audit["severity"] == "error"
    issue_codes = {issue["code"] for issue in audit["issues"]}
    warning_codes = {warning["code"] for warning in audit["warnings"]}
    assert "negative_currency" in issue_codes
    assert "negative_inventory_quantity" in issue_codes
    assert "legacy_inventory_entries" in warning_codes
    assert "inventory_requires_normalization" in warning_codes
    assert "missing_equipment_inventory_reference" in warning_codes
    assert "unknown_known_recipe" in warning_codes
    assert "mechanics_bucket_not_list" in warning_codes


def test_record_item_state_audit_persists_audit_trace_and_item_trace() -> None:
    state = {
        "player": {"inventory": [{"name": "Cloth", "material_id": "cloth", "quantity": 1}], "currency": {"copper": 4}},
        "mechanics": {"item_traces": [{"event": "existing"}]},
    }

    audit = record_item_state_audit(state)

    assert audit["trace"]["event"] == "item_state_audited"
    assert state["mechanics"]["item_state_audit_traces"][0] == audit["trace"]
    assert state["mechanics"]["item_traces"][0] == audit["trace"]
    assert state["mechanics"]["item_traces"][1] == {"event": "existing"}
