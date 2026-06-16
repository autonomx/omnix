from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import shared
from app.chat import ChatSessionStore, CreateChatSessionRequest, SendChatMessageRequest
from app.gateway.main import create_gateway_app
from app.jobs import SQLiteJobStore


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def chat_completion(self, *, messages, model, stream=False):
        prompt = messages[-1].content
        self.calls.append({"messages": messages, "model": model, "stream": stream, "prompt": prompt})
        return SimpleNamespace(
            content="Hello from the provider.",
            model=model or "default-model",
            usage={"total_tokens": 12},
            thinking="",
            reasoning="",
        )


def test_chat_store_invokes_provider_and_persists_assistant_message(monkeypatch, tmp_path):
    provider = FakeProvider()
    monkeypatch.setattr(shared, "get_provider", lambda provider_name=None: provider)
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")

    store = ChatSessionStore(tmp_path / "chat.json")
    session = store.create_session(
        CreateChatSessionRequest(
            title="New chat",
            provider_id="llm:lmstudio",
            model_id="llm:lmstudio:test-model",
        )
    )

    updated, user_message = store.append_user_message(
        session.id,
        SendChatMessageRequest(
            content="hey",
            provider_id="llm:lmstudio",
            model_id="llm:lmstudio:test-model",
        ),
    )

    assert user_message.role == "user"
    assert [message.role for message in updated.messages] == ["user", "assistant"]
    assert updated.messages[-1].content == "Hello from the provider."
    assert updated.messages[-1].metadata["generation_status"] == "completed"
    assert updated.messages[-1].metadata["resolved_model"] == "test-model"
    assert updated.message_count == 2

    assert len(provider.calls) == 1
    assert provider.calls[0]["model"] == "test-model"
    prompt_messages = provider.calls[0]["messages"]
    assert [message.role for message in prompt_messages] == ["system", "user"]
    assert prompt_messages[0].content == "System prompt"
    assert prompt_messages[1].content == "hey"

    reloaded = store.get_session(session.id)
    assert reloaded is not None
    assert reloaded.messages[-1].role == "assistant"
    assert reloaded.messages[-1].content == "Hello from the provider."


def _gateway_client(tmp_path, monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr(shared, "get_provider", lambda provider_name=None: provider)
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")
    store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    app = create_gateway_app(job_store_factory=lambda: store)
    return TestClient(app), provider


def test_story_jobs_execute_inline_and_complete(monkeypatch, tmp_path):
    client, provider = _gateway_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/jobs",
        json={
            "module": "storyteller",
            "type": "story.generate",
            "resource_class": "gpu:llm",
            "input_payload": {
                "title": "Lantern Road",
                "premise": "A courier follows a road.",
                "provider_id": "llm:lmstudio",
                "model_id": "llm:lmstudio:test-model",
            },
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "completed"
    assert payload["output_refs"][0]["type"] == "story"
    assert payload["output_refs"][0]["title"] == "Lantern Road"
    assert payload["output_refs"][0]["content"] == "Hello from the provider."
    assert provider.calls[0]["model"] == "test-model"
    assert "long-form story draft" in provider.calls[0]["prompt"]


def test_podcast_jobs_execute_inline_and_complete(monkeypatch, tmp_path):
    client, provider = _gateway_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/jobs",
        json={
            "module": "podcast",
            "type": "podcast.generate",
            "resource_class": "gpu:llm",
            "input_payload": {
                "title": "Market Watch",
                "brief": "Discuss local tools.",
                "speakers": ["Host", "Guest"],
                "provider_id": "llm:lmstudio",
                "model_id": "llm:lmstudio:test-model",
            },
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "completed"
    assert payload["output_refs"][0]["type"] == "podcast_script"
    assert payload["output_refs"][0]["title"] == "Market Watch"
    assert "podcast episode script" in provider.calls[0]["prompt"]


def test_rpg_turn_jobs_execute_inline_and_complete(monkeypatch, tmp_path):
    client, provider = _gateway_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/jobs",
        json={
            "module": "rpg",
            "type": "rpg.turn",
            "resource_class": "gpu:llm",
            "input_ref": {"session_id": "session:demo"},
            "input_payload": {
                "command": "look around",
                "provider_id": "llm:lmstudio",
                "model_id": "llm:lmstudio:test-model",
            },
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "completed"
    assert payload["output_refs"][0]["type"] == "rpg_turn_response"
    assert payload["output_refs"][0]["title"] == "look around"
    assert "RPG player command" in provider.calls[0]["prompt"]


def test_unsupported_jobs_still_use_queue_path(monkeypatch, tmp_path):
    client, _provider = _gateway_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/jobs",
        json={
            "module": "image-generation",
            "type": "image.generate",
            "resource_class": "gpu:image",
            "input_payload": {"prompt": "sample image"},
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "queued"
    assert payload["output_refs"] == []
