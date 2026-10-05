from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from tests.characterization.fakes import FakeLLMProvider, prompt_digest
from tests.characterization.harness import capture

# The catalog modules this scenario characterizes (scripts/test_module.py).
MODULES = ("chat",)


class RecordingChatStore:
    """Explicitly record the public stream route's transcript-store calls."""

    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate
        self.calls: list[dict[str, Any]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)

    def begin_user_message(self, session_id: str, request: Any, **kwargs: Any) -> Any:
        result = self.delegate.begin_user_message(session_id, request, **kwargs)
        self.calls.append(
            {
                "method": "begin_user_message",
                "session_id": session_id,
                "content": request.content,
            }
        )
        return result

    def begin_streaming_user_message(self, session_id: str, request: Any) -> Any:
        return self.begin_user_message(session_id, request, start_streaming=True)

    def stream_provider_reply_chunks(self, session: Any, user_message: Any, **kwargs: Any):
        self.calls.append(
            {
                "method": "stream_provider_reply_chunks",
                "session_id": session.id,
                "content": user_message.content,
                "provider_id": kwargs.get("provider_id"),
                "model_id": kwargs.get("model_id"),
            }
        )
        yield from self.delegate.stream_provider_reply_chunks(session, user_message, **kwargs)

    def complete_streamed_reply(
        self, session_id: str, user_message_id: str, content: str, metadata: dict[str, Any]
    ) -> Any:
        self.calls.append(
            {
                "method": "complete_streamed_reply",
                "session_id": session_id,
                "user_message_id": user_message_id,
                "content": content,
                "generation_status": metadata.get("generation_status"),
            }
        )
        return self.delegate.complete_streamed_reply(
            session_id, user_message_id, content, metadata
        )


def _parse_sse(payload: str) -> list[dict[str, Any]]:
    events = []
    for line in payload.splitlines():
        if not line.startswith("data: "):
            continue
        events.append(json.loads(line[6:]))
    return events


def test_chat_live_sse_turn_matches_pre_refactor_golden(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    from app.platform.chat import ChatSessionStore, CreateChatSessionRequest
    from app.composition.gateway.main import create_gateway_app
    from app.persistence import runtime
    from app.providers import service as provider_service
    from tests.support.in_memory_jobs import InMemoryJobStore
    from app.apps.desktop_companion import chat_activity

    class FakeActivityBridge:
        def record_user_turn(self, **_kwargs: Any) -> None:
            return None

    monkeypatch.setattr(runtime, "uses_postgresql_runtime", lambda: False)
    monkeypatch.setattr(provider_service, "get_global_system_prompt", lambda: "System prompt")
    monkeypatch.setattr(provider_service, "invalidate_provider_cache", lambda: None)
    monkeypatch.setattr(
        chat_activity,
        "default_desktop_companion_activity_bridge",
        lambda: FakeActivityBridge(),
    )

    prompt_messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "Summarize the current request."},
    ]
    provider = FakeLLMProvider(
        {
            prompt_digest(prompt_messages): (
                "The request is ready. ",
                "The provider is deterministic.",
            )
        }
    )
    monkeypatch.setattr(provider_service, "get_provider", lambda _name=None: provider)

    from app.platform.live_voice.chat_integration import create_live_voice_chat_port

    store = RecordingChatStore(
        ChatSessionStore(
            tmp_path / "chat.json",
            live_voice_chat_port=create_live_voice_chat_port(),
        )
    )
    session = store.create_session(
        CreateChatSessionRequest(
            title="Characterization",
            provider_id="fixture",
            model_id="fixture-model",
        )
    )
    app = create_gateway_app(
        job_store_factory=lambda: InMemoryJobStore(tmp_path / "jobs.sqlite"),
        chat_store_factory=lambda: store,
    )
    client = TestClient(
        app,
        base_url="http://127.0.0.1",
        headers={"X-Omnix-Client": "characterization"},
    )

    def scenario() -> dict[str, Any]:
        with caplog.at_level(logging.WARNING):
            response = client.post(
                f"/api/chat/sessions/{session.id}/messages/stream",
                json={
                    "content": "Summarize the current request.",
                    "provider_id": "fixture",
                    "model_id": "fixture-model",
                },
            )
        assert response.status_code == 200
        persisted = store.get_session(session.id)
        assert persisted is not None
        return {
            "content_type": response.headers.get("content-type"),
            "sse_events": _parse_sse(response.text),
            "persisted_messages": [
                message.model_dump(mode="json") for message in persisted.messages
            ],
            "store_calls": list(store.calls),
            "provider_calls": provider.calls,
            "warnings": [
                record.getMessage()
                for record in caplog.records
                if record.levelno >= logging.WARNING
            ],
        }

    capture("chat-live-sse-turn", scenario)
