from __future__ import annotations

from types import SimpleNamespace

from app.platform.assistant_memory.feature import FEATURE
from app.platform.assistant_memory.jobs import (
    MEMORY_SUGGEST_JOB_TYPE,
    create_memory_suggestion_job_request,
)
from app.jobs.handlers import JobExecutionContext
from app.jobs.models import JobStatus
from tests.support.in_memory_jobs import InMemoryJobStore


def test_assistant_memory_registers_durable_suggestion_handler(
    tmp_path,
    monkeypatch,
) -> None:
    handlers = {handler.type: handler for handler in FEATURE.job_handlers}
    assert MEMORY_SUGGEST_JOB_TYPE in handlers
    handler = handlers[MEMORY_SUGGEST_JOB_TYPE]

    store = InMemoryJobStore(tmp_path / "jobs")
    job = store.create_job(
        create_memory_suggestion_job_request("chat:missing", "msg:missing")
    )
    chat_store = SimpleNamespace(
        get_session=lambda _session_id: None,
        memory_service_factory=lambda: None,
    )
    monkeypatch.setattr(
        "app.platform.assistant_memory.feature.default_memory_service",
        lambda: None,
    )

    completed = handler.handler(
        JobExecutionContext(
            job_store=store,
            services=SimpleNamespace(chat=chat_store),
        ),
        job,
    )

    assert completed.status == JobStatus.COMPLETED
    assert completed.id == job.id
    persisted = store.get_job(job.id)
    assert persisted is not None
    assert persisted.status == JobStatus.COMPLETED
    assert persisted.logs[0]["event"] == "memory.suggestion.processed"
