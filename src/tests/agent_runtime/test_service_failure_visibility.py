from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.agent_runtime import service as service_module
from app.agent_runtime.contracts import AgentEvent, AgentRunCommand, AgentRunSnapshot, AgentRunSpec, ModelRef
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

    def apply_claimed(_command, *, reference_context=""):
        assert lock.held is True
        assert reference_context == ""
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


def test_recoverable_acceptance_failure_reprompts_active_runtime(monkeypatch) -> None:
    spec = AgentRunSpec(
        run_id="run-retry",
        task="Fix the code",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=["workspace.read", "workspace.edit", "workspace.test"],
    )
    snapshot = AgentRunSnapshot(run_id=spec.run_id, spec=spec, status="running")
    stored_events = [
        AgentEvent(
            run_id=spec.run_id,
            event_type="tool.started",
            payload={
                "tool_call_id": "test-1",
                "tool": "powershell",
                "args": {"command": "python -m pytest src/tests/live_speech -q"},
            },
        ),
        AgentEvent(
            run_id=spec.run_id,
            event_type="tool.completed",
            payload={
                "tool_call_id": "test-1",
                "tool": "powershell",
                "is_error": True,
                "result": {"details": {"exitCode": 1}},
            },
        ),
    ]
    updates: list[dict[str, object]] = []

    class _Repository:
        def latest_task_revision(self, _run_id):
            return None

        def append_event(self, event):
            stored_events.append(event)

        def list_events(self, _run_id, *, after_sequence=0, limit=5000):
            del after_sequence, limit
            return list(stored_events)

        def list_artifacts(self, _run_id):
            return []

        def list_evidence_receipts(self, _run_id):
            return []

        def get_run(self, _run_id):
            return snapshot

        def update_state(self, _run_id, **kwargs):
            updates.append(kwargs)
            return snapshot.model_copy(update=kwargs)

    dispatched = []
    service = object.__new__(AgentRunService)
    service.worker_id = "worker-1"
    service.runtime = SimpleNamespace(
        get_status=lambda _run_id: snapshot,
        command=lambda command: dispatched.append(command) or snapshot,
    )
    service._capture_diff = MagicMock()
    service._children_terminal_state = MagicMock(return_value=(True, False))
    monkeypatch.delenv("OMNIX_AGENT_ACCEPTANCE_RETRY_LIMIT", raising=False)

    service._finalize_acceptance(_Repository(), snapshot)

    assert len(dispatched) == 1
    assert dispatched[0].command_type == "resume"
    retry_message = str(dispatched[0].payload["message"])
    assert "Continue the same task; do not stop yet" in retry_message
    assert "unrelated passing test" in retry_message
    assert "pre-existing workspace change" in retry_message
    assert "successful_test_command" in retry_message
    assert any(event.event_type == "acceptance.retry_requested" for event in stored_events)
    completed = [
        event for event in stored_events
        if event.event_type == "acceptance.completed"
    ][-1]
    assert completed.payload["retrying"] is True
    assert updates[-1]["status"] == "running"
    assert updates[-1]["last_error"] is None


def test_acceptance_retry_transport_failure_terminalizes_run(monkeypatch) -> None:
    spec = AgentRunSpec(
        run_id="run-retry-transport-fail",
        task="Fix the code",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=["workspace.read", "workspace.edit", "workspace.test"],
    )
    snapshot = AgentRunSnapshot(run_id=spec.run_id, spec=spec, status="running")
    stored_events = [
        AgentEvent(
            run_id=spec.run_id,
            event_type="tool.started",
            payload={
                "tool_call_id": "test-1",
                "tool": "powershell",
                "args": {"command": "python -m pytest -q"},
            },
        ),
        AgentEvent(
            run_id=spec.run_id,
            event_type="tool.completed",
            payload={
                "tool_call_id": "test-1",
                "tool": "powershell",
                "is_error": True,
                "result": {"details": {"exitCode": 1}},
            },
        ),
    ]
    state = {"snapshot": snapshot}
    updates = []

    class _Repository:
        def latest_task_revision(self, _run_id):
            return None

        def append_event(self, event):
            stored_events.append(event)

        def list_events(self, _run_id, *, after_sequence=0, limit=5000):
            del after_sequence, limit
            return list(stored_events)

        def list_artifacts(self, _run_id):
            return []

        def list_evidence_receipts(self, _run_id):
            return []

        def get_run(self, _run_id):
            return state["snapshot"]

        def update_state(self, _run_id, **kwargs):
            updates.append(kwargs)
            state["snapshot"] = state["snapshot"].model_copy(update=kwargs)
            return state["snapshot"]

    service = object.__new__(AgentRunService)
    service.worker_id = "worker-1"
    service.runtime = SimpleNamespace(
        get_status=lambda _run_id: snapshot,
        command=lambda _command: (_ for _ in ()).throw(RuntimeError("Pi stopped")),
    )
    service._capture_diff = MagicMock()
    service._children_terminal_state = MagicMock(return_value=(True, False))
    monkeypatch.delenv("OMNIX_AGENT_ACCEPTANCE_RETRY_LIMIT", raising=False)

    service._finalize_acceptance(_Repository(), snapshot)

    assert updates[-1]["status"] == "failed"
    assert updates[-1]["desired_state"] == "cancelled"
    assert "acceptance_retry_failed:RuntimeError: Pi stopped" in str(updates[-1]["last_error"])
    assert any(event.event_type == "run.failed" for event in stored_events)


def test_acceptance_retry_count_is_scoped_to_task_revision() -> None:
    events = [
        AgentEvent(
            run_id="run-1",
            event_type="acceptance.retry_requested",
            payload={"task_revision_id": "revision-1"},
        ),
        AgentEvent(
            run_id="run-1",
            event_type="acceptance.retry_requested",
            payload={"task_revision_id": "revision-2"},
        ),
        AgentEvent(
            run_id="run-1",
            event_type="acceptance.retry_requested",
            payload={"task_revision_id": "revision-2"},
        ),
    ]

    assert service_module._acceptance_retry_count(events, "revision-1") == 1
    assert service_module._acceptance_retry_count(events, "revision-2") == 2
    assert service_module._acceptance_retry_count(events, None) == 0


def test_nonrecoverable_acceptance_failure_is_never_retried() -> None:
    assert service_module._acceptance_failures_retryable(
        ["modified_paths_outside_scope"]
    ) is False
    assert service_module._acceptance_failures_retryable(
        ["successful_test_command"]
    ) is True
