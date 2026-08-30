from __future__ import annotations

import subprocess
import threading
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import shared
from app.chat import ChatSessionStore, CreateChatSessionRequest, SendChatMessageRequest
from app.gateway.main import create_gateway_app
from app.jobs import InMemoryJobStore
from app.jobs.inline_feature_jobs import (
    INLINE_FEATURE_JOB_EXECUTOR_ENV,
    THREAD_EXECUTOR,
    _queue_deferred_rpg_turn_narration,
    _rpg_turn_visible_text,
)
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


class FailingProvider:
    def chat_completion(self, *, messages, model, stream=False):
        raise RuntimeError("Chat provider is not available")


def test_rpg_turn_visible_text_prefers_structured_narration() -> None:
    result = {
        "result": {
            "narration": (
                '"Bran," you begin.\n\nAction: You ask Bran about business.\n\n'
                'Result: You ask Bran about business.'
            ),
            "narration_json": {
                "narration": '"Bran," you begin, addressing him directly.',
                "npc": {
                    "speaker": "Bran",
                    "line": "Business is steady,' Bran replies. 'The local trade keeps us going.",
                },
            },
        }
    }

    assert _rpg_turn_visible_text(result) == (
        '"Bran," you begin, addressing him directly.\n\n'
        'Bran: "Business is steady," Bran replies. "The local trade keeps us going."'
    )


def test_rpg_turn_visible_text_displays_first_call_dialogue_response() -> None:
    result = {
        "player_input": "how is business bran?",
        "source": "first_call_dialogue_v1",
        "narration": "Bran glances toward the common room before answering.",
        "final_narration": "Bran glances toward the common room before answering.",
        "first_call_visible_response": {
            "consumable": True,
            "reason": "non_stateful_interpretive_dialogue",
            "visible_response": {
                "narration": "Bran glances toward the common room before answering.",
                "npc": {
                    "speaker": "Bran",
                    "line": "Steady enough. Rooms, food, and rumors keep the doors open.",
                },
            },
            "narration": "Bran glances toward the common room before answering.",
            "npc": {
                "speaker": "Bran",
                "line": "Steady enough. Rooms, food, and rumors keep the doors open.",
            },
        },
    }

    assert _rpg_turn_visible_text(result) == (
        "Bran glances toward the common room before answering.\n\n"
        'Bran: "Steady enough. Rooms, food, and rumors keep the doors open."'
    )


def test_rpg_turn_visible_text_skips_scene_restatement_narration() -> None:
    result = {
        "result": {
            "player_input": "I ask Bran if he has any food for sale",
            "narration": "Bran checks the available meal options.",
            "narration_json": {
                "narration": "I ask Bran if he has any food for sale",
                "npc": {
                    "speaker": "Scene",
                    "line": "I ask Bran if he has any food for sale",
                },
            },
        }
    }

    assert _rpg_turn_visible_text(result) == "Bran checks the available meal options."


def test_rpg_turn_visible_text_rejects_plain_player_restatement_after_bad_structured() -> None:
    result = {
        "input_payload": {
            "command": "i ask bran if he has food for sale",
        },
        "result": {
            "narration": "Scene\ni ask bran if he has food for sale",
            "narration_json": {
                "narration": "i ask bran if he has food for sale",
                "npc": {
                    "speaker": "Scene",
                    "line": "i ask bran if he has food for sale",
                },
            },
        }
    }

    assert _rpg_turn_visible_text(result) is None


def test_rpg_turn_visible_text_falls_back_for_direct_npc_business_question() -> None:
    result = {
        "input_payload": {
            "command": "i ask bran how business is going",
        },
        "result": {
            "narration_json": {
                "narration": "i ask bran how business is going",
                "npc": {
                    "speaker": "Scene",
                    "line": "i ask bran how business is going",
                },
            },
        },
    }

    assert _rpg_turn_visible_text(result) == (
        "Bran glances around the Rusty Flagon before answering.\n\n"
        'Bran: "Steady enough. Rooms, food, and rumors keep the doors open, '
        'though the road has been strange lately."'
    )


def test_rpg_turn_job_queues_deferred_narration(monkeypatch) -> None:
    from app.rpg.session import narration_worker
    from app.rpg.session import runtime

    saved_sessions: list[dict] = []
    signaled: list[str] = []

    def fake_enqueue(runtime_state, turn_id, tick, narration_request, job_kind="player_turn", priority=100):
        assert turn_id == "turn:12"
        assert tick == 12
        assert narration_request["session_id"] == "session:live"
        assert narration_request["performance"]["enable_live_narration_llm"] is True
        runtime_state["narration_jobs_by_turn"] = {
            turn_id: {"turn_id": turn_id, "status": "queued"}
        }
        return runtime_state, runtime_state["narration_jobs_by_turn"][turn_id], True

    monkeypatch.setattr(runtime, "load_runtime_session", lambda _session_id: {"runtime_state": {}})
    monkeypatch.setattr(runtime, "save_runtime_session", lambda session: saved_sessions.append(session) or session)
    monkeypatch.setattr(runtime, "_enqueue_narration_request", fake_enqueue)
    monkeypatch.setattr(narration_worker, "ensure_narration_worker_running", lambda: None)
    monkeypatch.setattr(narration_worker, "signal_narration_work", lambda session_id: signaled.append(session_id))

    result = {
        "ok": True,
        "result": {"narration": "Bran checks the goods.", "narration_status": "queued"},
        "narration_request": {
            "turn_id": "turn:12",
            "tick": 12,
            "performance": {"enable_live_narration_llm": False},
            "narration_context": {"player_input": "I buy rations"},
        },
    }

    assert _queue_deferred_rpg_turn_narration("session:live", result) is True
    assert result["narration_job"]["status"] == "queued"
    assert result["result"]["narration_status"] == "queued"
    assert saved_sessions[-1]["runtime_state"]["session_id"] == "session:live"
    assert signaled == ["session:live"]


def _wait_for_job_status(
    store: InMemoryJobStore,
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


def test_chat_endpoint_returns_provider_failure_instead_of_blank_500(monkeypatch, tmp_path):
    provider = FailingProvider()
    monkeypatch.setattr(shared, "get_provider", lambda provider_name=None: provider)
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")

    chat_store = ChatSessionStore(tmp_path / "chat.json")
    session = chat_store.create_session(
        CreateChatSessionRequest(
            title="Provider failure",
            provider_id="llm:lmstudio",
            model_id="llm:lmstudio:test-model",
        )
    )
    client = TestClient(
        create_gateway_app(
            chat_store_factory=lambda: chat_store,
            job_store_factory=lambda: InMemoryJobStore(tmp_path / "jobs.sqlite"),
        )
    )

    response = client.post(
        f"/api/chat/sessions/{session.id}/messages",
        json={
            "content": "hello",
            "provider_id": "llm:lmstudio",
            "model_id": "llm:lmstudio:test-model",
        },
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Chat generation failed: Chat provider is not available"
    }


def test_postgres_chat_store_initializes_prompt_context_cache(monkeypatch):
    from app.persistence import chat_runtime_compat

    repository = object()
    monkeypatch.setattr(
        chat_runtime_compat,
        "PostgresChatRepositoryAdapter",
        lambda: repository,
    )

    store = chat_runtime_compat.PostgresCharacterChatSessionStore()

    assert store._prompt_context_cache == {}
    assert store._prompt_context_cache_lock is not None
    assert store._repository is repository


def _gateway_client(tmp_path, monkeypatch, *, provider_content: str = "Hello from the provider."):
    monkeypatch.setenv(INLINE_FEATURE_JOB_EXECUTOR_ENV, THREAD_EXECUTOR)
    provider = FakeProvider(provider_content)
    monkeypatch.setattr(shared, "get_provider", lambda provider_name=None: provider)
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")
    store = InMemoryJobStore(tmp_path / "jobs.sqlite")
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


def test_rpg_turn_jobs_apply_authoritative_session_turn(monkeypatch, tmp_path):
    from app.rpg.session import interactive_first_call_runtime
    from app.rpg.session import service

    client, provider, store = _gateway_client(tmp_path, monkeypatch)
    applied: list[tuple[str, str, dict[str, object]]] = []
    saved_sessions: list[dict] = []

    def apply_turn(session_id: str, command: str, *, performance_override=None):
        applied.append((session_id, command, performance_override or {}))
        return {
            "ok": True,
            "session": {
                "state": {"player": {"currency": {"silver": 10}, "inventory": []}},
                "simulation_state": {
                    "player_state": {
                        "currency": {"silver": 5},
                        "inventory_state": {
                            "items": [{"item_id": "provisions", "name": "Provisions", "qty": 1}]
                        },
                    }
                },
            },
            "result": {"narration": "Bran takes five silver and hands Elara the registered provisions."},
            "turn_contract": {
                "presentation": {
                    "available_actions": [
                        {"label": "Buy provisions - 5 silver", "command": "I buy provisions from Bran"}
                    ]
                }
            },
        }

    monkeypatch.setattr(interactive_first_call_runtime, "apply_turn", apply_turn)
    monkeypatch.setattr(
        service,
        "load_session",
        lambda _session_id: {"state": {"player": {"currency": {"silver": 10}}}, "simulation_state": {}},
    )

    def save_session(session, compact=False):
        saved_sessions.append(session)
        return session

    monkeypatch.setattr(service, "save_session", save_session)
    response = client.post(
        "/api/jobs",
        json={
            "module": "rpg",
            "type": "rpg.turn",
            "resource_class": "gpu:llm",
            "input_ref": {"session_id": "session:live"},
            "input_payload": {"command": "I pay Bran five silver"},
        },
    )

    completed = _wait_for_job_status(store, response.json()["id"], {JobStatus.COMPLETED})
    assert applied == [
        (
            "session:live",
            "I pay Bran five silver",
            {"enable_live_narration_llm": False},
        )
    ]
    assert completed.output_refs[0]["content"] == (
        "Bran takes five silver and hands Elara the registered provisions."
    )
    assert saved_sessions[-1]["state"]["player"]["currency"] == {"silver": 5}
    assert saved_sessions[-1]["state"]["player"]["inventory"] == [
        {"id": "provisions", "name": "Provisions", "type": "item", "quantity": 1}
    ]
    assert provider.calls == []


def test_rpg_turn_jobs_return_before_background_completion(monkeypatch, tmp_path):
    monkeypatch.setenv(INLINE_FEATURE_JOB_EXECUTOR_ENV, THREAD_EXECUTOR)
    provider = BlockingProvider()
    monkeypatch.setattr(shared, "get_provider", lambda provider_name=None: provider)
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")
    store = InMemoryJobStore(tmp_path / "jobs.sqlite")
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
    store = InMemoryJobStore(tmp_path / "jobs.sqlite")

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
