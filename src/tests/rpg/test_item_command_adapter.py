from __future__ import annotations

from app.rpg.session.item_command_adapter import apply_item_command, normalize_item_command


def _state() -> dict:
    return {
        "current_turn": 9,
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


def test_normalize_text_pickup_and_effect_commands_with_state_lookup() -> None:
    state = _state()

    pickup = normalize_item_command("take Field Pack", state)
    effect = normalize_item_command("use Calm Focus", state)

    assert pickup["ok"] is True
    assert pickup["action"] == {"action": "pickup", "node_id": "field_pack", "source": "item_command_adapter"}
    assert effect["ok"] is True
    assert effect["action"] == {
        "action": "effect",
        "item_name": "Calm Focus",
        "source": "item_command_adapter",
        "effect_id": "steady",
    }
    assert effect["trace"]["mechanics_source"] == "engine_item_command_adapter_v1"


def test_normalize_dict_command_canonicalizes_action_and_preserves_payload() -> None:
    normalized = normalize_item_command({"kind": "collect", "node_id": "field_pack", "seed": 123})

    assert normalized["ok"] is True
    assert normalized["action"]["action"] == "pickup"
    assert normalized["action"]["node_id"] == "field_pack"
    assert normalized["action"]["seed"] == 123
    assert normalized["action"]["source"] == "item_command_adapter"


def test_apply_item_command_dispatches_and_records_command_traces() -> None:
    state = _state()

    result = apply_item_command(state, "use Calm Focus")

    assert result["ok"] is True
    assert result["normalized_action"]["action"] == "effect"
    assert state["player"]["resources"]["mana"]["current"] == 5
    assert state["player"]["inventory"] == []
    assert state["mechanics"]["item_command_traces"][0]["event"] == "item_command_applied"
    assert state["mechanics"]["item_command_traces"][0]["ok"] is True
    assert state["mechanics"]["item_traces"][0]["mechanics_source"] == "engine_item_command_adapter_v1"


def test_apply_item_command_can_record_report_command() -> None:
    state = _state()

    result = apply_item_command(state, "item report")

    assert result["ok"] is True
    assert result["session_action"] == "report"
    assert state["mechanics"]["item_report_sections"]
    assert state["mechanics"]["item_command_traces"][0]["result_action"] == "report"


def test_unknown_command_is_rejected_without_trace_noise() -> None:
    state = _state()

    result = apply_item_command(state, "sing about the moon")

    assert result == {
        "ok": False,
        "error": "unsupported_item_command",
        "command": "sing about the moon",
        "mechanics_source": "engine_item_command_adapter_v1",
    }
    assert state["mechanics"] == {}
