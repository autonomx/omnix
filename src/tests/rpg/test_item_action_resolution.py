from __future__ import annotations

from typing import Any

from app.rpg.session import item_action_resolution as resolver


def test_build_plan_for_text_command() -> None:
    plan = resolver.build_item_action_resolution_plan("item report")

    assert plan["handled"] is True
    assert plan["input_kind"] == "command"
    assert plan["command"] == "item report"
    assert plan["mechanics_source"] == resolver.ITEM_ACTION_RESOLUTION_SOURCE


def test_build_plan_for_nested_structured_action() -> None:
    plan = resolver.build_item_action_resolution_plan(
        {"action": "item_action", "item_action": {"action": "pickup", "node_id": "field_pack"}}
    )

    assert plan["handled"] is True
    assert plan["input_kind"] == "structured"
    assert plan["action_kind"] == "pickup"
    assert plan["action"]["node_id"] == "field_pack"


def test_build_plan_for_flat_structured_action() -> None:
    plan = resolver.build_item_action_resolution_plan(
        {"session_action": "effect", "item_name": "Calm Focus", "session_id": "ignored"}
    )

    assert plan["handled"] is True
    assert plan["input_kind"] == "structured"
    assert plan["action"] == {"item_name": "Calm Focus", "action": "effect"}


def test_build_plan_skips_non_item_action() -> None:
    plan = resolver.build_item_action_resolution_plan({"action": "travel", "destination": "market"})

    assert plan["handled"] is False
    assert plan["input_kind"] == "unknown"
    assert plan["reason"] == "non_item_action"


def test_apply_item_action_input_runs_command_wrapper(monkeypatch: Any) -> None:
    calls: list[dict[str, Any]] = []

    def fake_command(state: dict[str, Any], command: Any, **options: Any) -> dict[str, Any]:
        calls.append({"state": state, "command": command, "options": options})
        state["command_seen"] = command
        return {"ok": True, "detail": "command applied", "mechanics_source": "engine_item_command_adapter_v1"}

    monkeypatch.setattr(resolver, "apply_item_command_with_hooks", fake_command)
    state: dict[str, Any] = {}

    result = resolver.apply_item_action_input(
        state,
        "use Calm Focus",
        current_turn=7,
        station="workbench",
        genre="mythic",
        objective_limit=3,
    )

    assert result["ok"] is True
    assert result["handled"] is True
    assert result["resolver_mechanics_source"] == resolver.ITEM_ACTION_RESOLUTION_SOURCE
    assert result["resolution_plan"]["input_kind"] == "command"
    assert state["command_seen"] == "use Calm Focus"
    assert calls[0]["options"]["current_turn"] == 7
    assert calls[0]["options"]["station"] == "workbench"
    assert calls[0]["options"]["genre"] == "mythic"
    assert calls[0]["options"]["objective_limit"] == 3


def test_apply_item_action_input_runs_structured_wrapper(monkeypatch: Any) -> None:
    calls: list[dict[str, Any]] = []

    def fake_structured(state: dict[str, Any], action: dict[str, Any], **options: Any) -> dict[str, Any]:
        calls.append({"state": state, "action": action, "options": options})
        state["picked"] = action.get("node_id")
        return {"ok": True, "detail": "pickup applied", "mechanics_source": "engine_item_session_actions_v1"}

    monkeypatch.setattr(resolver, "apply_item_session_action_with_hooks", fake_structured)
    state: dict[str, Any] = {}

    result = resolver.apply_item_action_input(
        state,
        {"item_action": {"action": "pickup", "node_id": "field_pack"}},
        diagnostics_interval=1,
        maintenance_interval=2,
        report_interval=3,
    )

    assert result["ok"] is True
    assert result["handled"] is True
    assert result["resolution_plan"]["action_kind"] == "pickup"
    assert state["picked"] == "field_pack"
    assert calls[0]["action"] == {"action": "pickup", "node_id": "field_pack"}
    assert calls[0]["options"]["diagnostics_interval"] == 1
    assert calls[0]["options"]["maintenance_interval"] == 2
    assert calls[0]["options"]["report_interval"] == 3


def test_apply_item_action_input_skips_non_item_action_without_wrapper(monkeypatch: Any) -> None:
    def fail_command(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("command wrapper should not run")

    def fail_structured(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("structured wrapper should not run")

    monkeypatch.setattr(resolver, "apply_item_command_with_hooks", fail_command)
    monkeypatch.setattr(resolver, "apply_item_session_action_with_hooks", fail_structured)

    result = resolver.apply_item_action_input({}, {"action": "travel", "destination": "market"})

    assert result["ok"] is True
    assert result["handled"] is False
    assert result["skipped"] is True
    assert result["reason"] == "non_item_action"
