from datetime import datetime, timezone
from types import SimpleNamespace

from app.agent_runtime import chat_bridge
from app.agent_runtime.contracts import (
    AgentEvent,
    AgentRunSnapshot,
    AgentRunSpec,
    ModelRef,
)
from app.agent_runtime.service_core import (
    AgentRunService,
    _is_clarification_request,
)


class _Work:
    connection = object()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        pass

    def rollback(self):
        pass


class _Lock:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _event(text: str) -> AgentEvent:
    return AgentEvent(
        run_id="run-clarify",
        event_type="model.message",
        payload={"phase": "message_end", "text": text},
        created_at=datetime.now(timezone.utc),
    )


def test_clarification_detection_is_explicit_and_conservative() -> None:
    assert _is_clarification_request(_event("CLARIFICATION_REQUIRED: Which file should I change?"))
    assert _is_clarification_request(
        _event(
            "No specific implementation request was included—please tell me what behavior "
            "or visual change you want made."
        )
    )
    assert not _is_clarification_request(_event("I inspected the repository and found the chat header."))
    assert not _is_clarification_request(_event("The test asks what behavior the component should preserve."))


def test_clarification_event_pauses_run_for_user_input(monkeypatch) -> None:
    snapshot = AgentRunSnapshot(
        run_id="run-clarify",
        spec=AgentRunSpec(
            run_id="run-clarify",
            task="Fix the chat header",
            model=ModelRef(provider_id="test", model_id="model"),
        ),
        status="running",
    )
    state = {"snapshot": snapshot}
    appended = []
    updates = []

    class Repository:
        def __init__(self, _connection, _context):
            pass

        def get_run(self, _run_id):
            return state["snapshot"]

        def append_event(self, event):
            appended.append(event)

        def update_state(self, _run_id, **kwargs):
            updates.append(kwargs)
            state["snapshot"] = state["snapshot"].model_copy(update=kwargs)
            return state["snapshot"]

    service = object.__new__(AgentRunService)
    service.database = object()
    service.context = object()
    service.worker_id = "worker-1"
    service._lock = _Lock()
    monkeypatch.setattr("app.agent_runtime.service_core.unit_of_work", lambda _database: _Work())
    monkeypatch.setattr("app.agent_runtime.service_core.PostgresAgentRunRepository", Repository)

    service._persist_runtime_event(_event("CLARIFICATION_REQUIRED: Which header control should move?"))

    assert appended[-1].payload["requires_user_input"] is True
    assert updates[-1]["status"] == "waiting_for_input"
    assert updates[-1]["desired_state"] == "paused"


def test_pending_agent_clarification_routes_next_chat_message_to_run(monkeypatch) -> None:
    objective = {
        "objective_id": "run:run-clarify",
        "objective_type": "coding",
        "canonical_request": "Fix the chat header",
        "base_request": "Fix the chat header",
        "revisions": [],
        "status": "awaiting_user",
        "run_id": "run-clarify",
        "profile": "coding",
    }
    session = SimpleNamespace(
        id="session-1",
        provider_id="test",
        model_id="model",
        messages=[SimpleNamespace(role="assistant", metadata={"active_objective": objective})],
    )
    user_message = SimpleNamespace(
        id="message-2",
        content="Move fullscreen beside the voice selector.",
        metadata={},
    )
    spec = AgentRunSpec(
        run_id="run-clarify",
        session_id="session-1",
        task="Fix the chat header",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
    )
    snapshot = AgentRunSnapshot(
        run_id="run-clarify",
        spec=spec,
        status="waiting_for_input",
        desired_state="paused",
    )
    commands = []
    service = SimpleNamespace(
        get=lambda _run_id: snapshot,
        command_with_context=lambda command, **_kwargs: commands.append(command) or snapshot.model_copy(
            update={"status": "running", "desired_state": "running"}
        ),
    )
    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: service)

    result = chat_bridge.route_typed_chat_turn(
        session,
        user_message,
        provider_id="test",
        model_id="model",
        routing_context_factory=lambda: "",
    )

    assert result is not None
    assert "Steering sent to Agent run run-clarify." == result.content
    assert commands and commands[0].command_type == "steer"
    assert commands[0].payload["message"] == user_message.content
