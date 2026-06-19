from __future__ import annotations

from tests.rpg.autoplay.item_endurance_action_hook import (
    apply_item_endurance_milestone_to_result,
    apply_item_endurance_milestone_to_state,
    install_item_endurance_action_hook_from_argv,
)


def _runtime_state() -> dict:
    return {
        "inventory_state": {
            "currency": {"gold": 15, "silver": 8},
            "items": [
                {"item_id": "item:iron_dagger", "name": "Iron Dagger", "type": "weapon", "quantity": 1},
                {"item_id": "item:rations", "name": "Trail Rations", "type": "consumable", "quantity": 3},
                {"item_id": "item:journal", "name": "Plain Journal", "type": "tool", "quantity": 1},
            ],
        }
    }


def test_item_endurance_milestones_mutate_runtime_state_and_progress() -> None:
    state = _runtime_state()

    for turn in (5, 10, 15, 20, 30, 40, 55, 70, 85, 100):
        result = apply_item_endurance_milestone_to_state(state, turn_index=turn, total_turns=100)
        assert result["ok"] is True
        assert result["skipped"] is False

    mechanics = state["mechanics"]
    assert state["player"]["inventory"]
    assert state["inventory_state"]["items"] == state["player"]["inventory"]
    assert mechanics["pickup_traces"][0]["coverage_target"] == "pickup"
    assert mechanics["item_use_traces"][0]["coverage_target"] == "use_effect"
    assert mechanics["crafting_traces"][0]["coverage_target"] == "crafting"
    assert mechanics["market_traces"][0]["coverage_target"] == "merchant"
    assert mechanics["modification_traces"][0]["coverage_target"] == "modification"
    assert mechanics["item_combat_traces"][0]["coverage_target"] == "combat"
    assert mechanics["item_endurance_progress"]["ok"] is True
    assert mechanics["item_endurance_progress"]["coverage_score"] == 1.0


def test_item_endurance_result_hook_updates_simulation_state() -> None:
    result = {"ok": True, "simulation_state": _runtime_state()}

    applied = apply_item_endurance_milestone_to_result(result, turn_index=10, total_turns=100)

    assert applied["ok"] is True
    assert applied["skipped"] is False
    assert result["item_endurance_action_result"]["milestone"]["coverage_target"] == "pickup"
    assert result["simulation_state"]["mechanics"]["item_traces"][0]["coverage_target"] == "pickup"


def test_install_item_endurance_action_hook_wraps_call_turn_runtime() -> None:
    calls: list[int] = []

    def _call_turn_runtime(*, turn_index: int, simulation_state: dict, **_: object) -> dict:
        calls.append(turn_index)
        return {"ok": True, "simulation_state": simulation_state}

    namespace = {"_call_turn_runtime": _call_turn_runtime}
    install = install_item_endurance_action_hook_from_argv(namespace, ["--autoplay-profile", "smoke_100"])

    assert install["installed"] is True
    wrapped = namespace["_call_turn_runtime"]
    result = wrapped(turn_index=5, simulation_state=_runtime_state())

    assert calls == [5]
    assert result["item_endurance_action_result"]["milestone"]["coverage_target"] == "diagnostics"
    assert result["simulation_state"]["mechanics"]["item_traces"][0]["coverage_target"] == "diagnostics"
