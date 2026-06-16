from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import shared
from app.gateway.main import create_gateway_app
from app.jobs import SQLiteJobStore


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def chat_completion(self, *, messages, model, stream=False):
        prompt = messages[-1].content
        self.calls.append({"messages": messages, "model": model, "stream": stream, "prompt": prompt})
        return SimpleNamespace(content=f"generated: {prompt[:40]}", model=model or "fake-model")


def _client(tmp_path, monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr(shared, "get_provider", lambda provider_name=None: provider)
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")
    store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    app = create_gateway_app(job_store_factory=lambda: store)
    return TestClient(app), provider


def test_story_jobs_execute_inline_and_complete(tmp_path, monkeypatch):
    client, provider = _client(tmp_path, monkeypatch)
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
    assert payload["output_refs"][0]["content"].startswith("generated:")
    assert provider.calls[0]["model"] == "test-model"


def test_podcast_jobs_execute_inline_and_complete(tmp_path, monkeypatch):
    client, provider = _client(tmp_path, monkeypatch)
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


def test_rpg_turn_jobs_execute_inline_and_complete(tmp_path, monkeypatch):
    client, provider = _client(tmp_path, monkeypatch)
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


def test_unsupported_jobs_still_use_queue_path(tmp_path, monkeypatch):
    client, _provider = _client(tmp_path, monkeypatch)
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
