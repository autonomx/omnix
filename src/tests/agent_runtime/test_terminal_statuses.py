from __future__ import annotations

from pathlib import Path
import re
from typing import get_args

from app.platform.agent_runtime.contracts import TERMINAL_RUN_STATUSES, AgentRunSnapshot, AgentRunStatus
from app.platform.agent_runtime.task_graph import (
    TERMINAL_GRAPH_RUN_STATUSES,
    TERMINAL_NODE_RUN_STATUSES,
    TaskGraphRunStatus,
    TaskNodeRunStatus,
)

PACKAGE = Path(__file__).resolve().parents[2] / "app" / "platform" / "agent_runtime"


def test_terminal_sets_are_states_of_their_own_status_type() -> None:
    assert TERMINAL_RUN_STATUSES <= set(get_args(AgentRunStatus))
    assert TERMINAL_GRAPH_RUN_STATUSES <= set(get_args(TaskGraphRunStatus))
    assert TERMINAL_NODE_RUN_STATUSES <= set(get_args(TaskNodeRunStatus))
    assert TERMINAL_NODE_RUN_STATUSES - TERMINAL_GRAPH_RUN_STATUSES == {"skipped"}


def test_snapshot_knows_when_it_is_terminal() -> None:
    fields = AgentRunSnapshot.model_fields
    assert "is_terminal" not in fields
    for status in get_args(AgentRunStatus):
        snapshot = AgentRunSnapshot.model_construct(status=status)
        assert snapshot.is_terminal is (status in TERMINAL_RUN_STATUSES)


def test_run_and_graph_code_names_terminal_states_once() -> None:
    """Workflows keep their own status type; every other module uses the named sets."""
    spelled = re.compile(r'\bin \{"completed", "failed", "cancelled"(, "skipped")?\}')
    offenders = [
        path.name
        for path in PACKAGE.glob("*.py")
        if not path.name.startswith("workflow") and spelled.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
