from __future__ import annotations

import ast
from pathlib import Path
from typing import get_args

from app.agent_runtime.contracts import AgentEvent, AgentEventType


def test_planning_conformance_event_is_a_valid_agent_event() -> None:
    event = AgentEvent(
        run_id="run-planning-event",
        event_type="planning.conformance_evaluated",
        payload={"passed": True},
    )

    assert event.event_type == "planning.conformance_evaluated"


def _agent_event_call(node: ast.Call) -> bool:
    if isinstance(node.func, ast.Name):
        return node.func.id == "AgentEvent"
    if isinstance(node.func, ast.Attribute):
        return node.func.attr == "AgentEvent"
    return False


def test_literal_agent_event_emitters_are_registered_in_contract() -> None:
    """Fail CI when runtime code emits a literal event missing from AgentEventType."""

    runtime_root = Path(__file__).resolve().parents[2] / "app" / "agent_runtime"
    registered = set(get_args(AgentEventType))
    unknown: dict[str, list[str]] = {}

    for path in sorted(runtime_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _agent_event_call(node):
                continue
            for keyword in node.keywords:
                if keyword.arg != "event_type":
                    continue
                value = keyword.value
                if not (
                    isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                ):
                    continue
                if value.value not in registered:
                    relative = path.relative_to(runtime_root.parent.parent).as_posix()
                    unknown.setdefault(value.value, []).append(
                        f"{relative}:{getattr(node, 'lineno', '?')}"
                    )

    assert unknown == {}, (
        "AgentEvent emitters must be registered in AgentEventType before they can "
        f"ship: {unknown}"
    )
