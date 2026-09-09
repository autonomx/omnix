from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.agent_runtime.repository import PostgresAgentRunRepository


def test_repository_keeps_enqueue_command_compatibility_contract() -> None:
    source = (Path(__file__).parents[2] / "app" / "agent_runtime" / "repository.py").read_text(encoding="utf-8")
    assert "def enqueue_command(self, command: AgentRunCommand) -> AgentRunCommand:" in source
    assert "def enqueue_command_with_status" in source


def test_broker_reuses_durable_approval_for_execution_key() -> None:
    source = (Path(__file__).parents[2] / "app" / "agent_runtime" / "broker_api.py").read_text(encoding="utf-8")
    assert "find_capability_approval" in source


def test_latest_progress_query_ignores_control_plane_events() -> None:
    class Cursor:
        def fetchone(self):
            return (
                "event-1",
                12,
                "tool.completed",
                {"tool": "powershell"},
                None,
                None,
                datetime.now(timezone.utc),
            )

    class Connection:
        def __init__(self):
            self.query = ""

        def execute(self, query, _parameters):
            self.query = query
            return Cursor()

    connection = Connection()
    repository = PostgresAgentRunRepository(
        connection,
        SimpleNamespace(workspace_id="workspace-local"),
    )

    event = repository.latest_progress_event("run-1")

    assert event is not None
    assert event.event_type == "tool.completed"
    assert "event_type NOT IN" in connection.query
    for event_type in (
        "run.status",
        "approval.resolved",
        "steering.received",
        "run.recovery_requested",
    ):
        assert event_type in connection.query
