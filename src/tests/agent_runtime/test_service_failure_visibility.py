from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.agent_runtime import service as service_module
from app.agent_runtime.contracts import AgentRunCommand, AgentRunSnapshot, AgentRunSpec, ModelRef
from app.agent_runtime.service import AgentRunService


class _FakeWork:
    connection = object()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self) -> None:
        pass


class _TrackingLock:
    def __init__(self) -> None:
        self.held = False

    def __enter__(self):
        self.held = True
        return self

    def __exit__(self, *_args):
        self.held = False
        return False


def test_claimed_command_is_applied_while_runtime_events_are_serialized(monkeypatch) -> None:
    snapshot = AgentRunSnapshot(
        run_id="run-1",
        spec=AgentRunSpec(
            run_id="run-1",
            task="research",
            model=ModelRef(provider_id="test", model_id="model"),
        ),
        status="running",
    )
    command = AgentRunCommand(run_id="run-1", command_type="cancel")
    lock = _TrackingLock()

    class _Repository:
        def __init__(self, _connection, _context):
            pass

        def enqueue_command_with_status(self, _command):
            return command, "pending"

        def get_run(self, _run_id):
            return snapshot

        def claim_command(self, _run_id, _command_id):
            return True

        def complete_command(self, _run_id, _command_id):
            pass

    service = object.__new__(AgentRunService)
    service.database = object()
    service.context = object()
    service._lock = lock
    service._ensure_supervisor = MagicMock()
    service._cancel_descendants = MagicMock()
    service._maybe_finalize_parent_in_repository = MagicMock()
    service.get = MagicMock(return_value=snapshot)

    def apply_claimed(_command):
        assert lock.held is True
        return snapshot

    service._apply_claimed_command = apply_claimed
    monkeypatch.setattr(service_module, "unit_of_work", lambda _database: _FakeWork())
    monkeypatch.setattr(service_module, "PostgresAgentRunRepository", _Repository)

    service.command(command)

    assert lock.held is False


def test_command_failure_terminalizes_cancel_request(monkeypatch) -> None:
    snapshot = AgentRunSnapshot(
        run_id="run-1",
        spec=AgentRunSpec(
            run_id="run-1",
            task="research",
            model=ModelRef(provider_id="test", model_id="model"),
        ),
        status="cancel_requested",
        desired_state="cancelled",
    )
    updates = []
    completed = []

    class _Repository:
        def __init__(self, _connection, _context):
            pass

        def get_run(self, _run_id):
            return snapshot

        def update_state(self, run_id, **kwargs):
            updates.append((run_id, kwargs))
            return snapshot.model_copy(update=kwargs)

        def complete_command(self, run_id, command_id):
            completed.append((run_id, command_id))

    closed = []
    runtime = SimpleNamespace(close_run=lambda run_id: closed.append(run_id))
    service = object.__new__(AgentRunService)
    service.database = object()
    service.context = object()
    service.worker_id = "worker-1"
    service.runtime = runtime

    monkeypatch.setattr(service_module, "unit_of_work", lambda _database: _FakeWork())
    monkeypatch.setattr(service_module, "PostgresAgentRunRepository", _Repository)
    monkeypatch.setattr(service, "_cancel_descendants", lambda _run_id: None)

    command = AgentRunCommand(run_id="run-1", command_type="cancel")
    service._mark_command_failed(command, RuntimeError("Pi exited"))

    assert closed == ["run-1"]
    assert completed == [("run-1", command.command_id)]
    assert updates[0][0] == "run-1"
    assert updates[0][1]["status"] == "cancelled"
    assert updates[0][1]["desired_state"] == "cancelled"
    assert "Pi exited" in updates[0][1]["last_error"]
