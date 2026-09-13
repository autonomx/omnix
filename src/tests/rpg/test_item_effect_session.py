from __future__ import annotations

from app.rpg.session.item_effect_session import available_item_effects_for_session, apply_item_effect_for_session


def _state() -> dict:
    return {
        "current_turn": 7,
        "player": {
            "inventory": [
                {
                    "item_id": "calm_focus",
                    "name": "Calm Focus",
                    "item_type": "relic",
                    "quantity": 1,
                    "item_signals": [
                        {
                            "signal_id": "steady",
                            "op": "restore_resource",
                            "resource": "mana",
                            "amount": 4,
                            "consume": True,
                        }
                    ],
                },
                {
                    "item_id": "old_record",
                    "name": "Old Record",
                    "item_type": "relic",
                    "item_signals": [
                        {
                            "signal_id": "show_record",
                            "op": "add_affordance",
                            "bucket": "evidence",
                            "tag": "present_old_record",
                        }
                    ],
                },
            ],
            "resources": {"mana": {"current": 3, "max": 10}},
        },
        "mechanics": {},
    }


def test_available_item_effects_for_session_lists_inventory_contracts() -> None:
    state = _state()

    effects = available_item_effects_for_session(state)

    assert [entry["item_id"] for entry in effects] == ["calm_focus", "old_record"]
    assert effects[0]["effects"] == [{"id": "steady", "op": "restore_resource", "consume": True}]
    assert effects[1]["effects"][0]["id"] == "show_record"


def test_apply_item_effect_for_session_mutates_state_consumes_item_and_records_traces() -> None:
    state = _state()

    result = apply_item_effect_for_session(state, "Calm Focus", effect_id="steady", source="unit_test")

    assert result["ok"] is True
    assert result["consumed_item"] is True
    assert state["player"]["resources"]["mana"]["current"] == 7
    assert [item["item_id"] for item in state["player"]["inventory"]] == ["old_record"]
    trace = state["mechanics"]["item_effect_traces"][0]
    assert trace["session_event"] == "item_effect_session_applied"
    assert trace["session_source"] == "unit_test"
    assert trace["turn"] == 7
    assert trace["mechanics_source"] == "engine_item_effect_session_v1"
    assert state["mechanics"]["item_traces"][0] == trace


def test_apply_item_effect_for_session_preserves_non_consumed_item_and_affordance() -> None:
    state = _state()

    result = apply_item_effect_for_session(state, "Old Record", effect_id="show_record")

    assert result["ok"] is True
    assert result["consumed_item"] is False
    assert [item["item_id"] for item in state["player"]["inventory"]] == ["calm_focus", "old_record"]
    assert state["narrative_affordances"]["evidence"][0]["tag"] == "present_old_record"


def test_apply_item_effect_for_session_reports_missing_item_without_trace_noise() -> None:
    state = _state()

    result = apply_item_effect_for_session(state, "Missing")

    assert result["ok"] is False
    assert result["error"] == "item_not_found"
    assert state["mechanics"] == {}
