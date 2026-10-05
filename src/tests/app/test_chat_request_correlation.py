"""One request id follows a Chat submission into its job (WP-10.2 acceptance).

A submission through the gateway is admitted (request thread), dispatched to
the Chat worker, calls the provider (fake) and completes; every log line of
that path carries the submitting request's id.
"""
from __future__ import annotations

import io
import json
import logging
import threading
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.jobs.models import JobStatus
from app.observability.logging import configure_logging
from tests.characterization.fakes import FakeLLMProvider, prompt_digest
from tests.support.in_memory_jobs import InMemoryJobStore

logger = logging.getLogger("omnix.tests.chat_request_correlation")
REQUEST_ID = "trace-req-0001"


class _LoggingProvider(FakeLLMProvider):
    def chat_completion(self, **kwargs: Any) -> Any:
        logger.info("provider call")
        return super().chat_completion(**kwargs)


class _LoggingJobStore(InMemoryJobStore):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.finished = threading.Event()

    def create_job(self, request):
        job = super().create_job(request)
        logger.info("job admitted")
        return job

    def complete_job(self, job_id, request):
        logger.info("job completing")
        try:
            return super().complete_job(job_id, request)
        finally:
            self.finished.set()

    def fail_job(self, job_id, request):
        try:
            return super().fail_job(job_id, request)
        finally:
            self.finished.set()


def test_a_chat_submission_logs_one_request_id_from_admission_to_completion(tmp_path: Path, monkeypatch) -> None:
    from app.chat import ChatSessionStore, CreateChatSessionRequest
    from app.desktop_companion import chat_activity
    from app.gateway.main import create_gateway_app
    from app.live_voice.chat_integration import create_live_voice_chat_port
    from app.persistence import runtime
    from app.providers import service as provider_service

    class FakeActivityBridge:
        def record_user_turn(self, **_kwargs: Any) -> None:
            return None

    monkeypatch.setattr(runtime, "uses_postgresql_runtime", lambda: False)
    monkeypatch.setattr(provider_service, "get_global_system_prompt", lambda: "System prompt")
    monkeypatch.setattr(provider_service, "invalidate_provider_cache", lambda: None)
    monkeypatch.setattr(chat_activity, "default_desktop_companion_activity_bridge", lambda: FakeActivityBridge())
    prompt = [{"role": "system", "content": "System prompt"}, {"role": "user", "content": "Trace this turn."}]
    provider = _LoggingProvider({prompt_digest(prompt): "Traced."})
    monkeypatch.setattr(provider_service, "get_provider", lambda _name=None: provider)

    store = ChatSessionStore(tmp_path / "chat.json", live_voice_chat_port=create_live_voice_chat_port())
    session = store.create_session(
        CreateChatSessionRequest(title="Correlation", provider_id="fixture", model_id="fixture-model"),
    )
    job_store = _LoggingJobStore(tmp_path / "jobs.sqlite")
    app = create_gateway_app(job_store_factory=lambda: job_store, chat_store_factory=lambda: store)
    stream = io.StringIO()
    handler = configure_logging(log_format="json", level="INFO", stream=stream)
    try:
        response = TestClient(app, base_url="http://127.0.0.1").post(
            f"/api/chat/sessions/{session.id}/messages",
            json={"content": "Trace this turn.", "provider_id": "fixture", "model_id": "fixture-model"},
            headers={"X-Request-ID": REQUEST_ID, "X-Omnix-Client": "tests"},
        )
        assert response.status_code == 200, response.text
        job_id = response.json()["job"]["id"]
        assert job_store.finished.wait(10)
        job = job_store.get_job(job_id)
        assert job.status == JobStatus.COMPLETED, job.error
    finally:
        logging.getLogger().removeHandler(handler)

    assert response.headers["x-request-id"] == REQUEST_ID
    assert response.json()["job"]["correlation_id"] == REQUEST_ID
    lines = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
    traced = {line["message"]: line for line in lines if line["logger"] == logger.name}
    assert set(traced) == {"job admitted", "provider call", "job completing"}
    assert {line["request_id"] for line in traced.values()} == {REQUEST_ID}
    assert traced["provider call"]["job_id"] == traced["job completing"]["job_id"] == job_id
    assert all(line.get("request_id") == REQUEST_ID for line in lines if line.get("job_id") == job_id)
