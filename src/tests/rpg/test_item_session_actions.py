from __future__ import annotations

from app.rpg.session.item_session_actions import apply_item_session_action, available_item_session_actions


def _state() -> dict:
    return {
        "current_turn": 5,
        "player": {
            "inventory": [
                {
                    "item_id": "calm_focus",
                    "name": "Calm Focus",
                    "item_type": "relic",
                    "quantity": 1,
                    "item_signals": [
                        {"signal_id": "steady", "op": "restore_resource", "resource": "mana", "amount": 3, "consume": True}
                    ],
                }
            ],
            "resources": {"mana": {"current": 2, "max": 8}},
        },
        "scene_state": {
            "item_nodes": [
                {
                    "id": "field_pack",
                    "name": "Field Pack",
                    "remaining": 1,
                    "outputs": [{"item_id": "travel_ration", "name": "Travel ration", "quantity": 1, "stackable": True}],
                }
            ]
        },
        "mechanics": {},
    }


def test_available_item_session_actions_reports_pickups_and_effects() -> None:
    state = _state()

    available = available_item_session_actions(state)

    assert available["actions"]["pickup"] is True
    assert available["actions"]["effect"] is True
    assert available["pickups"][0]["node_id"] == "field_pack"
    assert available["effects"][0]["item_id"] == "calm_focus"
    assert available["mechanics_source"] == "engine_item_session_actions_v1"


def test_dispatcher_applies_pickup_effect_discovery_and_report_actions() -> None:
    state = _state()

    pickup = apply_item_session_action(state, {"action": "pickup", "node_id": "field_pack", "source": "unit"})
    effect = apply_item_session_action(state, {"action": "effect", "item_name": "Calm Focus", "effect_id": "steady"})
    discovery = apply_item_session_action(state, {"action": "recipe_discovery", "record_empty": True})
    report = apply_item_session_action(state, {"action": "report", "record": True})

    assert pickup["ok"] is True
    assert pickup["session_action"] == "pickup"
    assert effect["ok"] is True
    assert effect["session_action"] == "effect"
    assert state["player"]["resources"]["mana"]["current"] == 5
    assert discovery["ok"] is True
    assert discovery["recorded"] is True
    assert report["ok"] is True
    assert report["session_action"] == "report"
    assert state["mechanics"]["pickup_traces"]
    assert state["mechanics"]["item_effect_traces"]
    assert state["mechanics"]["recipe_discovery_traces"]
    assert state["mechanics"]["item_report_session_traces"]
    assert len(state["mechanics"]["item_traces"]) >= 4


def test_dispatcher_rejects_unknown_action_without_trace_noise() -> None:
    state = _state()

    result = apply_item_session_action(state, {"action": "dance"})

    assert result == {"ok": False, "error": "unsupported_item_session_action", "action": "dance"}
    assert state["mechanics"] == {}
