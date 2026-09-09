"""Contract tests for the gateway chat session API."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient


SRC_DIR = Path(__file__).resolve().parents[3]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _client(tmp_path: Path) -> TestClient:
    from app.chat import ChatSessionStore
    from app.gateway.main import create_gateway_app
    from app.jobs import InMemoryJobStore

    return TestClient(
        create_gateway_app(
            chat_store_factory=lambda: ChatSessionStore(tmp_path / "chat.json"),
            job_store_factory=lambda: InMemoryJobStore(tmp_path / "jobs.sqlite"),
        ),
        raise_server_exceptions=False,
    )


def _wait_for_job(client: TestClient, job_id: str, *, timeout: float = 2.0) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = client.get(f"/api/jobs/{job_id}").json()
        if last.get("status") in {"completed", "failed", "canceled", "stale"}:
            return last
        time.sleep(0.01)
    raise AssertionError(f"Job {job_id} did not finish: {last}")


def test_gateway_chat_sessions_are_backend_owned(tmp_path: Path) -> None:
    client = _client(tmp_path)

    created = client.post(
        "/api/chat/sessions",
        json={
            "title": "Workbench",
            "provider_id": "lmstudio",
            "model_id": "local-chat",
            "system_prompt": "Be concise.",
        },
    )

    assert created.status_code == 200
    session = created.json()
    assert session["title"] == "Workbench"
    assert session["provider_id"] == "lmstudio"
    assert session["messages"][0]["role"] == "system"

    listed = client.get("/api/chat/sessions")
    assert listed.status_code == 200
    assert listed.json()["sessions"][0]["id"] == session["id"]

    fetched = client.get(f"/api/chat/sessions/{session['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["messages"][0]["content"] == "Be concise."


def test_gateway_chat_message_queues_shared_generation_job(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    from app import shared

    monkeypatch.setattr(
        shared,
        "get_provider",
        lambda provider_name=None: SimpleNamespace(
            chat_completion=lambda **kwargs: SimpleNamespace(
                content="Provider response.",
                model=kwargs.get("model") or "gpt",
                usage={},
            )
        ),
    )
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")
    client = _client(tmp_path)
    session = client.post("/api/chat/sessions", json={"title": "Question"}).json()

    response = client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "Summarize the provider registry.", "provider_id": "openrouter", "model_id": "gpt"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["generation_status"] == "queued"
    assert payload["user_message"]["role"] == "user"
    assert payload["session"]["message_count"] == 1
    assert payload["session"]["messages"][-1]["content"] == "Summarize the provider registry."
    assert payload["job"]["module"] == "chatbot"
    assert payload["job"]["type"] == "chat.generate"
    assert payload["job"]["status"] == "running"
    assert payload["job"]["resource_class"] == "gpu:llm"
    assert payload["job"]["input_payload"]["session_id"] == session["id"]

    completed_job = _wait_for_job(client, payload["job"]["id"])
    assert completed_job["status"] == "completed"
    refreshed = client.get(f"/api/chat/sessions/{session['id']}").json()
    assert refreshed["message_count"] == 2
    assert refreshed["messages"][-1]["content"] == "Provider response."


def test_gateway_chat_submission_retry_reuses_message_and_job(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    from app import shared

    calls = 0

    def chat_completion(**kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(content="Only once.", model=kwargs.get("model") or "gpt", usage={})

    monkeypatch.setattr(shared, "get_provider", lambda provider_name=None: SimpleNamespace(chat_completion=chat_completion))
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")
    client = _client(tmp_path)
    session = client.post("/api/chat/sessions", json={"title": "Retry"}).json()
    body = {
        "content": "Do this once.",
        "provider_id": "openrouter",
        "model_id": "gpt",
        "user_turn_id": "web-user-turn:retry-1",
    }

    first = client.post(f"/api/chat/sessions/{session['id']}/messages", json=body)
    second = client.post(f"/api/chat/sessions/{session['id']}/messages", json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["job"]["id"] == first.json()["job"]["id"]
    assert second.json()["user_message"]["id"] == first.json()["user_message"]["id"]
    _wait_for_job(client, first.json()["job"]["id"])
    refreshed = client.get(f"/api/chat/sessions/{session['id']}").json()
    assert [message["role"] for message in refreshed["messages"]] == ["user", "assistant"]
    assert calls == 1


def test_gateway_chat_queue_failure_marks_user_turn_failed(tmp_path: Path) -> None:
    from app.chat import ChatSessionStore
    from app.gateway.main import create_gateway_app
    from app.jobs import InMemoryJobStore

    class FailingJobStore(InMemoryJobStore):
        def create_job(self, request):
            raise RuntimeError("queue unavailable")

    chat_store = ChatSessionStore(tmp_path / "chat.json")
    client = TestClient(
        create_gateway_app(
            chat_store_factory=lambda: chat_store,
            job_store_factory=lambda: FailingJobStore(tmp_path / "jobs.sqlite"),
        ),
        raise_server_exceptions=False,
    )
    session = client.post("/api/chat/sessions", json={"title": "Queue failure"}).json()

    response = client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "Please answer.", "user_turn_id": "web-user-turn:queue-failure"},
    )

    assert response.status_code == 503
    refreshed = client.get(f"/api/chat/sessions/{session['id']}").json()
    assert refreshed["messages"][-1]["metadata"]["generation_status"] == "failed"
    assert "queue unavailable" in refreshed["messages"][-1]["metadata"]["generation_error"]


def test_gateway_chat_cancel_cannot_commit_late_provider_reply(tmp_path: Path, monkeypatch) -> None:
    import threading
    from types import SimpleNamespace

    from app import shared

    entered = threading.Event()
    release = threading.Event()

    def chat_completion(**kwargs):
        entered.set()
        if not release.wait(timeout=2):
            raise RuntimeError("provider release timed out")
        return SimpleNamespace(content="Too late.", model=kwargs.get("model") or "gpt", usage={})

    monkeypatch.setattr(shared, "get_provider", lambda provider_name=None: SimpleNamespace(chat_completion=chat_completion))
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")
    client = _client(tmp_path)
    session = client.post("/api/chat/sessions", json={"title": "Cancel"}).json()
    accepted = client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "Wait for me.", "provider_id": "openrouter", "model_id": "gpt"},
    ).json()
    assert entered.wait(timeout=1)

    canceled = client.post(
        f"/api/jobs/{accepted['job']['id']}/cancel",
        json={"reason": "No longer needed"},
    )
    release.set()

    assert canceled.status_code == 200
    final_job = _wait_for_job(client, accepted["job"]["id"])
    assert final_job["status"] == "canceled"
    refreshed = client.get(f"/api/chat/sessions/{session['id']}").json()
    assert [message["role"] for message in refreshed["messages"]] == ["user"]
    assert refreshed["messages"][0]["metadata"]["generation_status"] == "canceled"


def test_gateway_serializes_generation_within_a_chat_session(tmp_path: Path, monkeypatch) -> None:
    import threading
    from types import SimpleNamespace

    from app import shared

    first_entered = threading.Event()
    first_release = threading.Event()
    second_entered = threading.Event()
    prompts: list[list[str]] = []

    def chat_completion(*, messages, model, stream=False):
        prompt = messages[-1].content
        prompts.append([message.content for message in messages])
        if prompt == "First turn":
            first_entered.set()
            if not first_release.wait(timeout=2):
                raise RuntimeError("first provider call was not released")
            content = "First answer"
        else:
            second_entered.set()
            content = "Second answer"
        return SimpleNamespace(content=content, model=model or "gpt", usage={})

    monkeypatch.setattr(shared, "get_provider", lambda provider_name=None: SimpleNamespace(chat_completion=chat_completion))
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")
    client = _client(tmp_path)
    session = client.post("/api/chat/sessions", json={"title": "Ordered"}).json()
    first = client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "First turn", "provider_id": "openrouter", "model_id": "gpt"},
    ).json()
    assert first_entered.wait(timeout=1)

    second = client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"content": "Second turn", "provider_id": "openrouter", "model_id": "gpt"},
    ).json()
    assert not second_entered.is_set()
    first_release.set()

    assert _wait_for_job(client, first["job"]["id"])["status"] == "completed"
    assert _wait_for_job(client, second["job"]["id"])["status"] == "completed"
    refreshed = client.get(f"/api/chat/sessions/{session['id']}").json()
    assert [(message["role"], message["content"]) for message in refreshed["messages"]] == [
        ("user", "First turn"),
        ("assistant", "First answer"),
        ("user", "Second turn"),
        ("assistant", "Second answer"),
    ]
    assert "First answer" in prompts[1]


def test_gateway_registers_quick_search_context_route_on_direct_main_import(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from types import SimpleNamespace

    from app import shared
    from app.assistant_context.models import AssistantContextItem
    from app.research.quick_search import QuickSearchExecution, QuickSearchService

    calls: list[dict[str, object]] = []

    def fake_chat_completion(*, messages, model, stream=False):
        calls.append({"messages": messages, "model": model, "stream": stream})
        return SimpleNamespace(content="France won 2-1.", model=model or "test-model", usage={})

    def fake_search(self, query, max_results=5, **kwargs):
        return QuickSearchExecution(
            items=[
                AssistantContextItem(
                    source_id="web_search",
                    title="FIFA result",
                    content="France beat Spain 2-1 in today's fixture.",
                    url="https://example.test/fifa-result",
                    metadata={"citation_label": "[1]"},
                )
            ],
            diagnostics={"status": "completed", "results": 1},
        )

    monkeypatch.setattr(shared, "get_provider", lambda provider_name=None: SimpleNamespace(chat_completion=fake_chat_completion))
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")
    monkeypatch.setattr(QuickSearchService, "search", fake_search)

    client = _client(tmp_path)
    session = client.post("/api/chat/sessions", json={"title": "Quick search"}).json()
    response = client.post(
        f"/api/assistant/context/chat/sessions/{session['id']}/messages",
        json={
            "content": "what was the result of todays fifa soccer games?",
            "web_research_mode": "quick",
            "provider_id": "llm:fixture",
            "model_id": "llm:fixture:test-model",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    completed_job = _wait_for_job(client, payload["job"]["id"])
    assert completed_job["status"] == "completed"
    refreshed = client.get(f"/api/chat/sessions/{session['id']}").json()
    assert refreshed["messages"][1]["metadata"]["context_sources"][0]["source_id"] == "web_search"
    assert refreshed["messages"][1]["metadata"]["context_sources"][0]["citation"] == "[1]"
    assert completed_job["input_payload"]["context_sources"] == ["web_search"]
    prompt = calls[0]["messages"][-1].content
    assert "Context retrieved for this turn follows." in prompt
    assert "France beat Spain 2-1 in today's fixture." in prompt
    assert prompt.endswith("what was the result of todays fifa soccer games?")


def test_context_completion_failure_removes_unvalidated_reply(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    from app import shared
    from app.assistant_context import routes
    from app.assistant_context.models import AssistantContextItem
    from app.research.quick_search import QuickSearchExecution, QuickSearchService

    monkeypatch.setattr(
        shared,
        "get_provider",
        lambda provider_name=None: SimpleNamespace(
            chat_completion=lambda **kwargs: SimpleNamespace(
                content="Unvalidated answer.",
                model=kwargs.get("model") or "test-model",
                usage={},
            )
        ),
    )
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")
    monkeypatch.setattr(
        QuickSearchService,
        "search",
        lambda self, query, max_results=5, **kwargs: QuickSearchExecution(
            items=[
                AssistantContextItem(
                    source_id="web_search",
                    title="Source",
                    content="Evidence",
                    metadata={"citation_label": "[1]"},
                )
            ],
            diagnostics={"status": "completed", "results": 1},
        ),
    )
    monkeypatch.setattr(
        routes,
        "validate_completed_research_reply",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("citation validation failed")),
    )
    client = _client(tmp_path)
    session = client.post("/api/chat/sessions", json={"title": "Validation"}).json()

    accepted = client.post(
        f"/api/assistant/context/chat/sessions/{session['id']}/messages",
        json={
            "content": "Research this.",
            "web_research_mode": "quick",
            "provider_id": "llm:fixture",
            "model_id": "llm:fixture:test-model",
        },
    ).json()

    final_job = _wait_for_job(client, accepted["job"]["id"])
    assert final_job["status"] == "failed"
    refreshed = client.get(f"/api/chat/sessions/{session['id']}").json()
    assert [message["role"] for message in refreshed["messages"]] == ["user"]
    assert refreshed["messages"][0]["metadata"]["generation_status"] == "failed"


def test_gateway_registers_desktop_context_for_streamed_chat(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from types import SimpleNamespace

    from app import shared
    from app.assistant_context.models import AssistantContextItem
    from app.assistant_context.vision import DesktopVisionClient

    calls: list[dict[str, object]] = []

    def fake_chat_completion(*, messages, model, stream=False):
        calls.append({"messages": messages, "model": model, "stream": stream})
        return [
            SimpleNamespace(content="I can see the desktop.", model=model, usage={}),
        ]

    def fake_describe(self, image_data_url, question, model_id=None, **kwargs):
        return AssistantContextItem(
            source_id="desktop_vision",
            title="Desktop observation",
            content="The shared desktop shows the Omnix chat window.",
        )

    monkeypatch.setattr(shared, "get_provider", lambda provider_name=None: SimpleNamespace(chat_completion=fake_chat_completion))
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")
    monkeypatch.setattr(DesktopVisionClient, "describe", fake_describe)

    client = _client(tmp_path)
    session = client.post("/api/chat/sessions", json={"title": "Desktop"}).json()
    response = client.post(
        f"/api/assistant/context/chat/sessions/{session['id']}/messages/stream",
        json={
            "content": "can you see the screen?",
            "web_research_mode": "disabled",
            "desktop_current_image_data_url": "data:image/jpeg;base64,AAAA",
            "provider_id": "llm:fixture",
            "model_id": "llm:fixture:test-model",
        },
    )

    assert response.status_code == 200
    assert '"type": "user_message"' in response.text
    assert '"type": "session"' in response.text
    assert '"desktop_vision"' in response.text
    prompt = calls[0]["messages"][-1].content
    assert "Context retrieved for this turn follows." in prompt
    assert "The shared desktop shows the Omnix chat window." in prompt
    assert prompt.endswith("can you see the screen?")
    assert calls[0]["stream"] is True


def test_gateway_chat_openapi_contract_is_published(tmp_path: Path) -> None:
    schema = _client(tmp_path).get("/openapi.json").json()

    assert "/api/chat/sessions" in schema["paths"]
    assert "/api/chat/sessions/{session_id}" in schema["paths"]
    assert "/api/chat/sessions/{session_id}/messages" in schema["paths"]
