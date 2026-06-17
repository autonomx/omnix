from __future__ import annotations

import subprocess
import threading
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import shared
from app.chat import ChatSessionStore, CreateChatSessionRequest, SendChatMessageRequest
from app.gateway.main import create_gateway_app
from app.jobs import SQLiteJobStore
from app.jobs.inline_feature_jobs import INLINE_FEATURE_JOB_EXECUTOR_ENV, THREAD_EXECUTOR
from app.jobs.models import CreateJobRequest, JobRecord, JobStatus, ResourceClass


class FakeProvider:
    def __init__(self, content: str = "Hello from the provider.") -> None:
        self.calls: list[dict[str, object]] = []
        self.content = content

    def chat_completion(self, *, messages, model, stream=False):
        prompt = messages[-1].content
        self.calls.append({"messages": messages, "model": model, "stream": stream, "prompt": prompt})
        return SimpleNamespace(
            content=self.content,
            model=model or "default-model",
            usage={"total_tokens": 12},
            thinking="",
            reasoning="",
        )


class BlockingProvider(FakeProvider):
    def __init__(self, content: str = "Delayed RPG response.") -> None:
        super().__init__(content)
        self.entered = threading.Event()
        self.release = threading.Event()

    def chat_completion(self, *, messages, model, stream=False):
        prompt = messages[-1].content
        self.calls.append({"messages": messages, "model": model, "stream": stream, "prompt": prompt})
        self.entered.set()
        if not self.release.wait(timeout=2):
            raise RuntimeError("Blocking test provider was not released")
        return SimpleNamespace(
            content=self.content,
            model=model or "default-model",
            usage={"total_tokens": 12},
            thinking="",
            reasoning="",
        )


def _wait_for_job_status(
    store: SQLiteJobStore,
    job_id: str,
    statuses: set[JobStatus],
    *,
    timeout: float = 2,
) -> JobRecord:
    deadline = time.monotonic() + timeout
    last_job = None
    while time.monotonic() < deadline:
        last_job = store.get_job(job_id)
        if last_job is not None and last_job.status in statuses:
            return last_job
        time.sleep(0.01)
    last_status = last_job.status.value if last_job is not None else "missing"
    expected = ", ".join(sorted(status.value for status in statuses))
    raise AssertionError(f"Job {job_id} did not reach {expected}; last status was {last_status}")


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


def _gateway_client(tmp_path, monkeypatch, *, provider_content: str = "Hello from the provider."):
    monkeypatch.setenv(INLINE_FEATURE_JOB_EXECUTOR_ENV, THREAD_EXECUTOR)
    provider = FakeProvider(provider_content)
    monkeypatch.setattr(shared, "get_provider", lambda provider_name=None: provider)
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")
    store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    app = create_gateway_app(job_store_factory=lambda: store)
    return TestClient(app), provider, store


def test_story_jobs_execute_inline_and_complete(monkeypatch, tmp_path):
    client, provider, _store = _gateway_client(tmp_path, monkeypatch)

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


def test_story_jobs_with_empty_title_generate_title(monkeypatch, tmp_path):
    client, provider, _store = _gateway_client(
        tmp_path,
        monkeypatch,
        provider_content="# Lantern Road\n\nA courier follows a road lit by patient stars.",
    )

    response = client.post(
        "/api/jobs",
        json={
            "module": "storyteller",
            "type": "story.generate",
            "resource_class": "gpu:llm",
            "input_payload": {
                "title": "",
                "premise": "A courier follows a road.",
                "provider_id": "llm:lmstudio",
                "model_id": "llm:lmstudio:test-model",
                "generate_title": True,
                "interaction_mode": "story",
                "source_text": "Player response: I follow the road.",
            },
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "completed"
    assert payload["output_refs"][0]["title"] == "Lantern Road"
    assert payload["output_refs"][0]["content"].startswith("# Lantern Road")
    assert "Generate an evocative, concise title" in provider.calls[0]["prompt"]
    assert "Story context:" in provider.calls[0]["prompt"]
    assert "Player response: I follow the road." in provider.calls[0]["prompt"]


def test_podcast_jobs_execute_inline_and_complete(monkeypatch, tmp_path):
    client, provider, _store = _gateway_client(tmp_path, monkeypatch)

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


def test_rpg_turn_jobs_execute_in_background_and_complete(monkeypatch, tmp_path):
    client, provider, store = _gateway_client(tmp_path, monkeypatch)

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
    assert payload["status"] == "queued"
    assert payload["output_refs"] == []

    completed = _wait_for_job_status(store, payload["id"], {JobStatus.COMPLETED})
    assert completed.output_refs[0]["type"] == "rpg_turn_response"
    assert completed.output_refs[0]["title"] == "look around"
    assert "RPG player command" in provider.calls[0]["prompt"]


def test_rpg_turn_jobs_return_before_background_completion(monkeypatch, tmp_path):
    monkeypatch.setenv(INLINE_FEATURE_JOB_EXECUTOR_ENV, THREAD_EXECUTOR)
    provider = BlockingProvider()
    monkeypatch.setattr(shared, "get_provider", lambda provider_name=None: provider)
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")
    store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    app = create_gateway_app(job_store_factory=lambda: store)
    client = TestClient(app)

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
    assert payload["status"] == "queued"
    assert payload["output_refs"] == []
    try:
        assert provider.entered.wait(timeout=1)
        running = _wait_for_job_status(store, payload["id"], {JobStatus.RUNNING})
        assert running.output_refs == []
    finally:
        provider.release.set()

    completed = _wait_for_job_status(store, payload["id"], {JobStatus.COMPLETED})
    assert completed.output_refs[0]["content"] == "Delayed RPG response."


def test_rpg_turn_jobs_spawn_detached_worker_process_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv(INLINE_FEATURE_JOB_EXECUTOR_ENV, raising=False)
    launched: list[dict[str, object]] = []

    class FakePopen:
        def __init__(self, command, **kwargs) -> None:
            launched.append({"command": command, "kwargs": kwargs})

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    store = SQLiteJobStore(tmp_path / "jobs.sqlite")

    job = store.create_job(
        CreateJobRequest(
            module="rpg",
            type="rpg.turn",
            resource_class=ResourceClass.GPU_LLM,
            input_payload={"command": "look around"},
        )
    )

    assert job.status == JobStatus.QUEUED
    assert launched
    command = launched[0]["command"]
    assert isinstance(command, list)
    assert command[-3:] == ["app.jobs.inline_feature_job_worker", str(tmp_path / "jobs.sqlite"), job.id]
    assert launched[0]["kwargs"]["stdin"] == subprocess.DEVNULL
    assert launched[0]["kwargs"]["stdout"] == subprocess.DEVNULL
    assert launched[0]["kwargs"]["stderr"] == subprocess.DEVNULL
    stored_job = store.get_job(job.id)
    assert stored_job is not None
    assert stored_job.status == JobStatus.QUEUED


def test_unsupported_jobs_still_use_queue_path(monkeypatch, tmp_path):
    client, _provider, _store = _gateway_client(tmp_path, monkeypatch)

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
