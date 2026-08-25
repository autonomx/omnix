"""Offload post-turn memory extraction from the response/request thread."""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from functools import wraps
from typing import Any

from app.assistant_memory.jobs import (
    enqueue_memory_suggestion_job,
    process_memory_suggestion_job,
)
from app.assistant_memory.structured_provider import (
    default_structured_proposal_provider,
)
from app.chat.prompt_store import ChatSessionStore as PromptChatSessionStore
from app.jobs import FailJobRequest, default_job_store

from .tts_stream_diagnostics import stream_log

_SENTINEL = "_omnix_memory_job_offload_installed"
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="omnix-memory-post-turn")


def _mark_failure(job_id: str, future: Future[Any]) -> None:
    error = future.exception()
    if error is None:
        return
    default_job_store().fail_job(
        job_id,
        FailJobRequest(
            code="memory_suggestion_background_failed",
            message=str(error)[:500] or "Memory suggestion job failed.",
            retryable=True,
        ),
    )
    stream_log(
        "gateway-live-chat-first-token",
        "runtime",
        "memory_suggestion_background_failed",
        job_id=job_id,
        error_type=type(error).__name__,
    )


def _process_background_job(job, *, chat_store, memory_service):
    if callable(memory_service):
        memory_service = memory_service()
    return process_memory_suggestion_job(
        job,
        chat_store=chat_store,
        memory_service=memory_service,
        proposal_provider=default_structured_proposal_provider(),
    )


def install_memory_job_offload_hook() -> None:
    """Make suggestion processing asynchronous while retaining durable job state."""

    if getattr(PromptChatSessionStore, _SENTINEL, False):
        return
    original = PromptChatSessionStore._enqueue_memory_suggestion_job

    @wraps(original)
    def patched(self: PromptChatSessionStore, session_id: str, user_message_id: str) -> None:
        job = enqueue_memory_suggestion_job(session_id, user_message_id)
        if job is None:
            return
        future = _EXECUTOR.submit(
            _process_background_job,
            job,
            chat_store=self,
            memory_service=self.memory_service_factory,
        )
        future.add_done_callback(lambda completed: _mark_failure(job.id, completed))
        stream_log(
            "gateway-live-chat-first-token",
            "runtime",
            "memory_suggestion_background_dispatched",
            job_id=job.id,
            session_id=session_id,
        )

    PromptChatSessionStore._enqueue_memory_suggestion_job = patched
    setattr(PromptChatSessionStore, _SENTINEL, True)


__all__ = ["install_memory_job_offload_hook"]
