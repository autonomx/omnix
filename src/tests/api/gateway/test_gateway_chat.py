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


def test_gateway_chat_message_queues_shared_generation_job(tmp_path: Path) -> None:
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
    assert payload["job"]["module"] == "chatbot"
    assert payload["job"]["type"] == "chat.generate"
    assert payload["job"]["resource_class"] == "gpu:llm"
    assert payload["job"]["input_payload"]["session_id"] == session["id"]

    jobs = client.get("/api/jobs").json()["jobs"]
    assert jobs[0]["id"] == payload["job"]["id"]


def test_gateway_chat_openapi_contract_is_published(tmp_path: Path) -> None:
    schema = _client(tmp_path).get("/openapi.json").json()

    assert "/api/chat/sessions" in schema["paths"]
    assert "/api/chat/sessions/{session_id}" in schema["paths"]
    assert "/api/chat/sessions/{session_id}/messages" in schema["paths"]
