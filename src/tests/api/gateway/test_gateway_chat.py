"""Contract tests for the gateway chat session API."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


SRC_DIR = Path(__file__).resolve().parents[3]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _client(tmp_path: Path) -> TestClient:
    from app.chat import ChatSessionStore
    from app.gateway.main import create_gateway_app
    from app.jobs import SQLiteJobStore

    return TestClient(
        create_gateway_app(
            chat_store_factory=lambda: ChatSessionStore(tmp_path / "chat.json"),
            job_store_factory=lambda: SQLiteJobStore(tmp_path / "jobs.sqlite"),
        ),
        raise_server_exceptions=False,
    )


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
    assert payload["session"]["message_count"] == 2
    assert payload["session"]["messages"][-1]["content"] == "Provider response."
    assert payload["job"]["module"] == "chatbot"
    assert payload["job"]["type"] == "chat.generate"
    assert payload["job"]["resource_class"] == "gpu:llm"
    assert payload["job"]["input_payload"]["session_id"] == session["id"]

    jobs = client.get("/api/jobs").json()["jobs"]
    assert jobs[0]["id"] == payload["job"]["id"]


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
    assert payload["user_message"]["metadata"]["context_sources"][0]["source_id"] == "web_search"
    assert payload["job"]["input_payload"]["context_sources"] == ["web_search"]
    prompt = calls[0]["messages"][-1].content
    assert "Context retrieved for this turn follows." in prompt
    assert "France beat Spain 2-1 in today's fixture." in prompt
    assert prompt.endswith("what was the result of todays fifa soccer games?")


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
