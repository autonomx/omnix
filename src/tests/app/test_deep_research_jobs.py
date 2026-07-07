from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.assistant_context.routes import register_assistant_context_routes
from app.chat import ChatSessionStore, CreateChatSessionRequest
from app.jobs import CancelJobRequest, SQLiteJobStore
from app.jobs.research_inline import (
    DeepResearchWorkflowResult,
    execute_research_job,
    load_research_checkpoint,
    save_research_checkpoint,
)
from app.research.executor import ResearchExecutionCheckpoint
from app.research.planner import ResearchOperation, ResearchPlan


class ContextServiceMustNotRun:
    def build(self, request):
        raise AssertionError("Deep Research must not build synchronous assistant context")


def test_deep_research_route_returns_user_turn_and_queued_job_before_generation(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OMNIX_INLINE_RESEARCH_JOB_EXECUTOR", "0")
    chat_store = ChatSessionStore(tmp_path / "chat.json")
    job_store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    session = chat_store.create_session(CreateChatSessionRequest(title="Deep research"))
    app = FastAPI()
    register_assistant_context_routes(
        app,
        chat_store_factory=lambda: chat_store,
        job_store_factory=lambda: job_store,
        context_service_factory=ContextServiceMustNotRun,
    )
    response = TestClient(app).post(
        f"/api/assistant/context/chat/sessions/{session.id}/messages",
        json={"content": "Compare the current options", "web_research_mode": "deep"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["generation_status"] == "queued"
    assert payload["job"]["type"] == "assistant.deep_research"
    assert payload["job"]["status"] == "queued"
    assert [stage["id"] for stage in payload["job"]["stages"]] == [
        "planning", "searching", "extracting", "evaluating", "synthesizing", "persisting"
    ]
    saved = chat_store.get_session(session.id)
    assert saved is not None
    assert [message.role for message in saved.messages] == ["user"]
    assert saved.messages[0].metadata["research_job_id"] == payload["job"]["id"]


def test_deep_research_executor_persists_partial_message_and_completes_shared_job(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OMNIX_INLINE_RESEARCH_JOB_EXECUTOR", "0")
    chat_store = ChatSessionStore(tmp_path / "chat.json")
    job_store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    session = chat_store.create_session(CreateChatSessionRequest(title="Deep research"))
    app = FastAPI()
    register_assistant_context_routes(
        app,
        chat_store_factory=lambda: chat_store,
        job_store_factory=lambda: job_store,
        context_service_factory=ContextServiceMustNotRun,
    )
    response = TestClient(app).post(
        f"/api/assistant/context/chat/sessions/{session.id}/messages",
        json={"content": "Research this", "web_research_mode": "deep"},
    )
    job = job_store.get_job(response.json()["job"]["id"])
    assert job is not None

    completed = execute_research_job(
        job_store,
        job,
        chat_store=chat_store,
        workflow_fn=lambda request, progress, canceled: DeepResearchWorkflowResult(
            content="Best available answer.\n\n## Limitations\nOne source was unavailable.",
            research_status="partial",
            source_manifest_id="manifest:deep",
            output={"conflicts": []},
        ),
    )

    assert completed.status.value == "completed"
    assert completed.output_refs[0]["research_status"] == "partial"
    saved = chat_store.get_session(session.id)
    assert saved is not None
    assert [message.role for message in saved.messages] == ["user", "assistant"]
    assistant = saved.messages[-1]
    assert assistant.metadata["research_status"] == "partial"
    assert assistant.metadata["research_job_id"] == job.id
    assert assistant.metadata["source_manifest_id"] == "manifest:deep"


def test_research_checkpoint_round_trips_on_job_stage(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_INLINE_RESEARCH_JOB_EXECUTOR", "0")
    chat_store = ChatSessionStore(tmp_path / "chat.json")
    job_store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    session = chat_store.create_session(CreateChatSessionRequest(title="Checkpoint research"))
    app = FastAPI()
    register_assistant_context_routes(
        app,
        chat_store_factory=lambda: chat_store,
        job_store_factory=lambda: job_store,
        context_service_factory=ContextServiceMustNotRun,
    )
    response = TestClient(app).post(
        f"/api/assistant/context/chat/sessions/{session.id}/messages",
        json={"content": "Research this", "web_research_mode": "deep"},
    )
    job_id = response.json()["job"]["id"]
    plan = ResearchPlan(
        objective="Research this",
        operations=[
            ResearchOperation(operation="web_search", query="research this"),
            ResearchOperation(operation="stop", reason="done"),
        ],
    )
    checkpoint = ResearchExecutionCheckpoint(
        objective=plan.objective,
        plan=plan,
        planner_backend="local",
        next_operation_index=1,
        logical_queries=1,
    )

    save_research_checkpoint(job_store, job_id, "searching", checkpoint)
    restored = load_research_checkpoint(job_store, job_id)

    assert restored is not None
    assert restored.next_operation_index == 1
    assert restored.logical_queries == 1
    assert restored.plan.operations[0].query == "research this"


def test_deep_research_executor_acknowledges_cancellation(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_INLINE_RESEARCH_JOB_EXECUTOR", "0")
    chat_store = ChatSessionStore(tmp_path / "chat.json")
    job_store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    session = chat_store.create_session(CreateChatSessionRequest(title="Cancel research"))
    app = FastAPI()
    register_assistant_context_routes(
        app,
        chat_store_factory=lambda: chat_store,
        job_store_factory=lambda: job_store,
        context_service_factory=ContextServiceMustNotRun,
    )
    response = TestClient(app).post(
        f"/api/assistant/context/chat/sessions/{session.id}/messages",
        json={"content": "Research this", "web_research_mode": "deep"},
    )
    job_id = response.json()["job"]["id"]
    job_store.cancel_job(job_id, CancelJobRequest(reason="User canceled"))
    job = job_store.get_job(job_id)
    assert job is not None

    canceled = execute_research_job(job_store, job, chat_store=chat_store)

    assert canceled.status.value == "canceled"
    assert canceled.cancel.acknowledged_at
    saved = chat_store.get_session(session.id)
    assert saved is not None
    assert [message.role for message in saved.messages] == ["user"]
