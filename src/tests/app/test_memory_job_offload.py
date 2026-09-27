from __future__ import annotations

from app.gateway import memory_job_offload
from concurrent.futures import Future


def test_background_memory_job_resolves_structured_provider_inside_worker(monkeypatch) -> None:
    sentinel_provider = object()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        memory_job_offload,
        "default_structured_proposal_provider",
        lambda: sentinel_provider,
    )

    def fake_process(job, **kwargs):
        captured["job"] = job
        captured.update(kwargs)
        return "processed"

    monkeypatch.setattr(
        memory_job_offload,
        "process_memory_suggestion_job",
        fake_process,
    )

    result = memory_job_offload._process_background_job(
        "job:one",
        chat_store="chat-store",
        memory_service="memory-service",
    )

    assert result == "processed"
    assert captured == {
        "job": "job:one",
        "chat_store": "chat-store",
        "memory_service": "memory-service",
        "proposal_provider": sentinel_provider,
    }


def test_background_memory_job_resolves_memory_service_inside_worker(monkeypatch) -> None:
    sentinel_service = object()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        memory_job_offload,
        "default_structured_proposal_provider",
        lambda: object(),
    )

    def fake_process(job, **kwargs):
        captured["job"] = job
        captured.update(kwargs)
        return "processed"

    monkeypatch.setattr(memory_job_offload, "process_memory_suggestion_job", fake_process)

    result = memory_job_offload._process_background_job(
        "job:two",
        chat_store="chat-store",
        memory_service=lambda: sentinel_service,
    )

    assert result == "processed"
    assert captured["memory_service"] is sentinel_service


def test_failure_callback_reports_without_mutating_an_unowned_job(monkeypatch):
    events = []
    monkeypatch.setattr(memory_job_offload, "stream_log", lambda *args, **kwargs: events.append(kwargs))
    future = Future()
    future.set_exception(RuntimeError("provider failed"))
    memory_job_offload._mark_failure("job:failed", future)
    assert events == [{"job_id": "job:failed", "error_type": "RuntimeError"}]


def test_canceled_dispatch_does_not_raise_from_failure_callback(monkeypatch):
    monkeypatch.setattr(memory_job_offload, "stream_log", lambda *_args, **_kwargs: None)
    future = Future()
    future.cancel()
    memory_job_offload._mark_failure("job:canceled", future)
