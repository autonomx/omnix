from __future__ import annotations

from typing import Any

from app.rpg.session.item_session_with_hooks import (
    apply_item_command_with_hooks,
    apply_item_session_action_with_hooks,
    run_item_session_action_hooks,
)


def _state() -> dict[str, Any]:
    return {
        "current_turn": 10,
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
                            "amount": 3,
                            "consume": True,
                        }
                    ],
                }
            ],
            "resources": {"mana": {"current": 2, "max": 8}},
        },
        "mechanics": {},
    }


def test_apply_item_session_action_with_hooks_runs_turn_hooks_for_effect() -> None:
    state = _state()

    result = apply_item_session_action_with_hooks(
        state,
        {"action": "effect", "item_name": "Calm Focus", "effect_id": "steady"},
        diagnostics_interval=10,
        maintenance_interval=25,
        report_interval=20,
        objective_limit=3,
    )

    assert result["ok"] is True
    assert result["session_action"] == "effect"
    assert result["item_hook_result"]["skipped"] is False
    assert "recipe_discovery" in result["item_hook_result"]["executed_actions"]
    assert "diagnostics" in result["item_hook_result"]["executed_actions"]
    assert state["player"]["resources"]["mana"]["current"] == 5
    assert state["mechanics"]["item_session_action_hook_traces"][0]["action"] == "effect"
    assert state["mechanics"]["item_turn_hook_traces"]


def test_apply_item_command_with_hooks_uses_normalized_action() -> None:
    state = _state()

    result = apply_item_command_with_hooks(state, "use Calm Focus", diagnostics_interval=10)

    assert result["ok"] is True
    assert result["normalized_action"]["action"] == "effect"
    assert result["item_hook_result"]["action"] == "effect"
    assert result["item_hook_result"]["skipped"] is False
    assert state["mechanics"]["item_command_traces"]
    assert state["mechanics"]["item_session_action_hook_traces"]


def test_session_action_hooks_skip_report_actions_to_avoid_report_loops() -> None:
    state = _state()

    result = run_item_session_action_hooks(
        state,
        action={"action": "report"},
        result={"ok": True, "session_action": "report", "mechanics_source": "engine_item_session_actions_v1"},
    )

    assert result == {
        "ok": True,
        "skipped": True,
        "turn": 10,
        "action": "report",
        "reason": "non_hooked_item_session_action",
        "recorded": False,
        "mechanics_source": "engine_item_session_with_hooks_v1",
    }
    assert state["mechanics"] == {}


def test_session_action_hooks_skip_non_engine_results_for_testability() -> None:
    state = _state()

    result = run_item_session_action_hooks(
        state,
        action={"action": "pickup"},
        result={"ok": True, "session_action": "pickup"},
    )

    assert result["skipped"] is True
    assert result["reason"] == "non_engine_result_source"
    assert state["mechanics"] == {}
