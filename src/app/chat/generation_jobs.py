"""Background execution for accepted Chat generation jobs."""
from __future__ import annotations

import logging
import queue
import threading
from collections import defaultdict, deque
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from app.jobs import CancelJobRequest, CompleteJobRequest, FailJobRequest
from app.jobs.models import JobRecord, JobStatus

from .models import ChatMessage, ChatSession, SendChatMessageRequest

logger = logging.getLogger(__name__)

ContextBuilder = Callable[[], tuple[list[dict[str, Any]], dict[str, Any]]]
CompletionHook = Callable[[Any, str, str, list[dict[str, Any]], dict[str, Any]], None]

_CHAT_WORKER_COUNT = 4
_ACTIVE_JOB_STATUSES = {
    JobStatus.QUEUED,
    JobStatus.LEASED,
    JobStatus.RUNNING,
    JobStatus.WAITING,
    JobStatus.RETRYING,
}
_registry_guard = threading.Lock()
_submission_locks: dict[tuple[str, str], threading.RLock] = {}
_job_commit_locks: dict[str, threading.RLock] = {}


@dataclass(frozen=True)
class _ChatGenerationWork:
    chat_store: Any
    job_store: Any
    job: JobRecord
    request: SendChatMessageRequest
    context_builder: ContextBuilder | None
    completion_hook: CompletionHook | None


class _ChatGenerationDispatcher:
    """Bound local execution while preserving turn order within each session."""

    def __init__(self, worker_count: int = _CHAT_WORKER_COUNT) -> None:
        self._worker_count = worker_count
        self._ready_sessions: queue.Queue[str] = queue.Queue()
        self._pending: dict[str, deque[_ChatGenerationWork]] = defaultdict(deque)
        self._scheduled: set[str] = set()
        self._lock = threading.Lock()
        self._started = False

    def submit(self, work: _ChatGenerationWork) -> None:
        session_id = str((work.job.input_payload or {}).get("session_id") or "").strip()
        if not session_id:
            session_id = f"missing-session:{work.job.id}"
        with self._lock:
            self._pending[session_id].append(work)
            if session_id not in self._scheduled:
                self._scheduled.add(session_id)
                self._ready_sessions.put(session_id)
            if not self._started:
                self._started = True
                for index in range(self._worker_count):
                    threading.Thread(
                        target=self._worker,
                        name=f"omnix-chat-worker-{index + 1}",
                        daemon=True,
                    ).start()

    def _worker(self) -> None:
        while True:
            session_id = self._ready_sessions.get()
            work: _ChatGenerationWork | None = None
            with self._lock:
                pending = self._pending.get(session_id)
                if pending:
                    work = pending.popleft()
            try:
                if work is not None:
                    _run_chat_generation_job(
                        chat_store=work.chat_store,
                        job_store=work.job_store,
                        job=work.job,
                        request=work.request,
                        context_builder=work.context_builder,
                        completion_hook=work.completion_hook,
                    )
            except Exception:
                logger.exception(
                    "Unhandled Chat generation worker failure for job %s; worker will continue",
                    getattr(getattr(work, "job", None), "id", "unknown"),
                )
            finally:
                with self._lock:
                    pending = self._pending.get(session_id)
                    if pending:
                        self._ready_sessions.put(session_id)
                    else:
                        self._pending.pop(session_id, None)
                        self._scheduled.discard(session_id)
                self._ready_sessions.task_done()


_dispatcher = _ChatGenerationDispatcher()


def _registry_lock(registry: dict[Any, threading.RLock], key: Any) -> threading.RLock:
    with _registry_guard:
        return registry.setdefault(key, threading.RLock())


@contextmanager
def chat_submission_lock(session_id: str, submission_id: str | None):
    """Serialize idempotent acceptance for one browser submission."""

    key = (session_id, submission_id or f"anonymous:{threading.get_ident()}")
    lock = _registry_lock(_submission_locks, key)
    with lock:
        yield


@contextmanager
def chat_job_commit_lock(job_id: str):
    """Make cancellation and final transcript persistence mutually exclusive."""

    lock = _registry_lock(_job_commit_locks, job_id)
    with lock:
        yield


def find_chat_generation_job(
    job_store: Any,
    *,
    session_id: str,
    submission_id: str | None,
) -> JobRecord | None:
    if not submission_id:
        return None
    find = getattr(job_store, "find_job_by_submission", None)
    if callable(find):
        return find(
            job_type="chat.generate",
            session_id=session_id,
            submission_id=submission_id,
        )
    for job in job_store.list_jobs(limit=500):
        if (
            job.type == "chat.generate"
            and isinstance(job.input_ref, dict)
            and job.input_ref.get("session_id") == session_id
            and isinstance(job.input_payload, dict)
            and job.input_payload.get("submission_id") == submission_id
        ):
            return job
    return None


def existing_chat_generation_turn(
    chat_store: Any,
    job: JobRecord,
) -> tuple[ChatSession, ChatMessage] | None:
    payload = job.input_payload or {}
    session_id = str(payload.get("session_id") or "").strip()
    message_id = str(payload.get("message_id") or "").strip()
    session = chat_store.get_session(session_id) if session_id else None
    if session is None:
        return None
    message = _find_user_message(session, message_id)
    return (session, message) if message is not None else None


def mark_chat_acceptance_failed(
    chat_store: Any,
    *,
    session_id: str,
    message_id: str,
    error: Exception,
) -> None:
    message = " ".join(str(error).split()).strip() or type(error).__name__
    try:
        _patch_user_message_metadata(
            chat_store,
            session_id=session_id,
            message_id=message_id,
            metadata={"generation_status": "failed", "generation_error": message[:500]},
        )
    except Exception:
        logger.warning("Could not mark unqueued Chat message %s failed", message_id, exc_info=True)
    _mark_assistant_turn_failed(chat_store, session_id, message_id)


def start_chat_generation_job(
    *,
    chat_store: Any,
    job_store: Any,
    job: JobRecord,
    request: SendChatMessageRequest,
    context_builder: ContextBuilder | None = None,
    completion_hook: CompletionHook | None = None,
) -> JobRecord:
    """Queue local Chat generation after the job has been durably accepted."""

    # Inline jobs are marked before dispatch so generic queue workers cannot
    # claim them during the small handoff window. The dispatcher still bounds
    # provider execution and serializes work for each session.
    started = job_store.mark_running(job.id) or job
    _dispatcher.submit(
        _ChatGenerationWork(
            chat_store=chat_store,
            job_store=job_store,
            job=started,
            request=request,
            context_builder=context_builder,
            completion_hook=completion_hook,
        )
    )
    return started


def cancel_chat_generation_job(
    chat_store: Any,
    job_store: Any,
    job_id: str,
    request: CancelJobRequest,
) -> JobRecord | None:
    """Cancel without racing the final transcript/job commit."""

    with chat_job_commit_lock(job_id):
        current = job_store.get_job(job_id)
        if current is None:
            return None
        if current.status in {
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELED,
            JobStatus.STALE,
        }:
            return current
        canceled = job_store.cancel_job(job_id, request) or current
        if current.status in {JobStatus.QUEUED, JobStatus.WAITING, JobStatus.RETRYING}:
            payload = current.input_payload or {}
            session_id = str(payload.get("session_id") or "").strip()
            message_id = str(payload.get("message_id") or "").strip()
            if session_id and message_id:
                _cancel_chat_turn(chat_store, job_store, current, session_id, message_id)
            return job_store.get_job(job_id) or canceled
        return canceled


def recover_abandoned_chat_generation_jobs(chat_store: Any, job_store: Any) -> int:
    """Fail process-local Chat jobs left non-terminal by an earlier gateway."""

    recovered = 0
    for job in job_store.list_jobs(limit=500):
        if (
            job.type != "chat.generate"
            or not job.compat.get("inline_execution")
            or job.status not in _ACTIVE_JOB_STATUSES | {JobStatus.CANCEL_REQUESTED}
        ):
            continue
        payload = job.input_payload or {}
        session_id = str(payload.get("session_id") or "").strip()
        message_id = str(payload.get("message_id") or "").strip()
        if job.status == JobStatus.CANCEL_REQUESTED:
            if session_id and message_id:
                _cancel_chat_turn(chat_store, job_store, job, session_id, message_id)
            else:
                _finalize_job_cancel(job_store, job.id)
        else:
            _fail_job(
                chat_store,
                job_store,
                job,
                RuntimeError("Gateway restarted before Chat generation completed."),
                session_id=session_id or None,
                message_id=message_id or None,
            )
        recovered += 1
    return recovered


def _run_chat_generation_job(
    *,
    chat_store: Any,
    job_store: Any,
    job: JobRecord,
    request: SendChatMessageRequest,
    context_builder: ContextBuilder | None,
    completion_hook: CompletionHook | None,
) -> None:
    payload = job.input_payload or {}
    session_id = str(payload.get("session_id") or "").strip()
    message_id = str(payload.get("message_id") or "").strip()
    if not session_id or not message_id:
        _fail_job(
            chat_store,
            job_store,
            job,
            RuntimeError("Chat generation job is missing its session or message identity."),
        )
        return

    try:
        _update_progress(job_store, job.id, "Preparing response")
        context_items: list[dict[str, Any]] = []
        context_diagnostics: dict[str, Any] = {}
        if context_builder is not None:
            context_items, context_diagnostics = context_builder()
            _patch_user_message_metadata(
                chat_store,
                session_id=session_id,
                message_id=message_id,
                metadata={
                    "context_sources": _context_source_summaries(context_items),
                    "context_diagnostics": context_diagnostics,
                },
            )
            _update_job_input(
                job_store,
                job,
                {
                    **payload,
                    "context_sources": [
                        str(item.get("source_id") or "context")
                        for item in context_items
                    ],
                    "context_diagnostics": context_diagnostics,
                },
            )

        if _cancel_requested(job_store, job.id):
            _cancel_chat_turn(chat_store, job_store, job, session_id, message_id)
            return

        session = chat_store.get_session(session_id)
        if session is None:
            raise RuntimeError("Chat session not found while generation was starting.")
        user_index = next(
            (
                index
                for index, item in enumerate(session.messages)
                if item.id == message_id and item.role == "user"
            ),
            None,
        )
        if user_index is None:
            raise RuntimeError("Chat user message not found while generation was starting.")
        # A later accepted turn may already be durable. Generate against only
        # the transcript through this turn; the per-session dispatcher will
        # add this reply before the next turn starts.
        session = session.model_copy(
            update={
                "messages": session.messages[: user_index + 1],
                "message_count": user_index + 1,
            }
        )
        user_message = session.messages[-1]

        _mark_assistant_turn_streaming(user_message)
        _update_progress(job_store, job.id, "Generating response")
        answer = _generate_reply(
            chat_store,
            session,
            user_message,
            request=request,
            context_items=context_items,
        )
        if not answer:
            raise RuntimeError("Chat generation ended without a response.")
        content = str(answer.get("content") or "").strip()
        metadata = dict(answer.get("metadata") or {})
        metadata["reply_to_message_id"] = message_id
        with chat_job_commit_lock(job.id):
            if _cancel_requested(job_store, job.id):
                _cancel_chat_turn(chat_store, job_store, job, session_id, message_id)
                return
            _persist_routing_metadata(chat_store, session, user_message)
            if context_items:
                metadata["context_sources"] = _context_source_summaries(context_items)
                metadata["context_diagnostics"] = context_diagnostics
            completed = chat_store.complete_streamed_reply(
                session_id,
                message_id,
                content,
                metadata,
            )
            if completed is None:
                raise RuntimeError("Chat response could not be persisted.")
            if completion_hook is not None:
                try:
                    completion_hook(
                        chat_store,
                        session_id,
                        message_id,
                        context_items,
                        context_diagnostics,
                    )
                except Exception:
                    _remove_assistant_reply(chat_store, session_id, message_id)
                    raise
            completed_job = job_store.complete_job(
                job.id,
                CompleteJobRequest(
                    output_refs=[
                        {
                            "type": "chat_response",
                            "module": "chatbot",
                            "session_id": session_id,
                            "message_id": message_id,
                            "content": content,
                        }
                    ],
                    logs=[
                        {
                            "level": "info",
                            "message": "Chat response generated and persisted.",
                            "session_id": session_id,
                            "message_id": message_id,
                        }
                    ],
                ),
            )
            if completed_job is None:
                raise RuntimeError("Chat generation completed but its job disappeared.")
    except Exception as exc:  # pragma: no cover - exercised through job state
        _fail_job(chat_store, job_store, job, exc, session_id=session_id, message_id=message_id)


def _fail_job(
    chat_store: Any,
    job_store: Any,
    job: JobRecord,
    error: Exception,
    *,
    session_id: str | None = None,
    message_id: str | None = None,
) -> None:
    message = " ".join(str(error).split()).strip() or type(error).__name__
    current = job_store.get_job(job.id)
    if current is None or current.status in {
        JobStatus.COMPLETED,
        JobStatus.FAILED,
        JobStatus.CANCELED,
        JobStatus.STALE,
    }:
        return
    if current.status == JobStatus.CANCEL_REQUESTED:
        if session_id and message_id:
            _cancel_chat_turn(chat_store, job_store, job, session_id, message_id)
        else:
            _finalize_job_cancel(job_store, job.id)
        return
    if session_id and message_id:
        try:
            _patch_user_message_metadata(
                chat_store,
                session_id=session_id,
                message_id=message_id,
                metadata={"generation_status": "failed", "generation_error": message[:500]},
            )
        except Exception:
            logger.warning("Could not mark failed Chat message %s", message_id, exc_info=True)
        _mark_assistant_turn_failed(chat_store, session_id, message_id)
    try:
        job_store.fail_job(
            job.id,
            FailJobRequest(
                code="chat_generation_failed",
                message=message[:500],
                retryable=True,
                details={
                    key: value
                    for key, value in {
                        "session_id": session_id,
                        "message_id": message_id,
                    }.items()
                    if value
                },
            ),
        )
    except Exception:
        logger.exception("Could not fail Chat generation job %s", job.id)


def _cancel_chat_turn(
    chat_store: Any,
    job_store: Any,
    job: JobRecord,
    session_id: str,
    message_id: str,
) -> None:
    try:
        _patch_user_message_metadata(
            chat_store,
            session_id=session_id,
            message_id=message_id,
            metadata={"generation_status": "canceled"},
        )
    except Exception:
        logger.warning("Could not mark canceled Chat message %s", message_id, exc_info=True)
    _mark_assistant_turn_canceled(chat_store, session_id, message_id)
    _finalize_job_cancel(job_store, job.id)


def _finalize_job_cancel(job_store: Any, job_id: str) -> None:
    finalize = getattr(job_store, "finalize_cancel", None)
    if callable(finalize):
        finalize(job_id, "Chat generation canceled.")
    else:
        job_store.cancel_job(job_id, CancelJobRequest(reason="Chat generation canceled."))


def _cancel_requested(job_store: Any, job_id: str) -> bool:
    current = job_store.get_job(job_id)
    return current is None or current.status in {
        JobStatus.CANCEL_REQUESTED,
        JobStatus.CANCELED,
    }


def _update_progress(job_store: Any, job_id: str, message: str) -> None:
    update = getattr(job_store, "update_progress", None)
    if callable(update):
        update(job_id, current=0, total=1, message=message)


def _update_job_input(job_store: Any, job: JobRecord, payload: dict[str, Any]) -> None:
    update = getattr(job_store, "update_job_input", None)
    if callable(update):
        update(job.id, payload)


def _find_user_message(session: ChatSession, message_id: str) -> ChatMessage | None:
    return next(
        (
            message
            for message in session.messages
            if message.id == message_id and message.role == "user"
        ),
        None,
    )


def _assistant_turn_id(user_message: ChatMessage) -> str:
    return str(user_message.metadata.get("assistant_turn_id") or "").strip()


def _mark_assistant_turn_streaming(user_message: ChatMessage) -> None:
    assistant_turn_id = _assistant_turn_id(user_message)
    if not assistant_turn_id:
        return
    from .assistant_turns import default_assistant_turn_coordinator

    default_assistant_turn_coordinator().mark_streaming(assistant_turn_id)


def _mark_assistant_turn_canceled(chat_store: Any, session_id: str, message_id: str) -> None:
    user_message = _load_user_message(chat_store, session_id, message_id)
    assistant_turn_id = _assistant_turn_id(user_message) if user_message is not None else ""
    if not assistant_turn_id:
        return
    try:
        from .assistant_turns import default_assistant_turn_coordinator

        coordinator = default_assistant_turn_coordinator()
        coordinator.request_cancel(assistant_turn_id, "Chat generation canceled.")
        coordinator.mark_provider_cancelled(assistant_turn_id)
    except Exception:
        logger.warning("Could not mark assistant turn %s canceled", assistant_turn_id, exc_info=True)


def _mark_assistant_turn_failed(chat_store: Any, session_id: str, message_id: str) -> None:
    user_message = _load_user_message(chat_store, session_id, message_id)
    assistant_turn_id = _assistant_turn_id(user_message) if user_message is not None else ""
    if not assistant_turn_id:
        return
    try:
        from .assistant_turns import default_assistant_turn_coordinator

        default_assistant_turn_coordinator().mark_failed(assistant_turn_id)
    except Exception:
        logger.warning("Could not mark assistant turn %s failed", assistant_turn_id, exc_info=True)


def _load_user_message(chat_store: Any, session_id: str, message_id: str) -> ChatMessage | None:
    session = chat_store.get_session(session_id)
    return _find_user_message(session, message_id) if session is not None else None


def _remove_assistant_reply(chat_store: Any, session_id: str, message_id: str) -> None:
    remove = getattr(chat_store, "remove_assistant_reply", None)
    if callable(remove):
        remove(session_id, message_id)
        return
    sessions = chat_store._load_sessions()
    for index, session in enumerate(sessions):
        if session.id != session_id:
            continue
        session.messages = [
            item
            for item in session.messages
            if not (
                item.role == "assistant"
                and item.metadata.get("reply_to_message_id") == message_id
            )
        ]
        session.message_count = len(session.messages)
        sessions[index] = session
        chat_store._save_sessions(sessions)
        return


def _generate_reply(
    chat_store: Any,
    session: ChatSession,
    user_message: ChatMessage,
    *,
    request: SendChatMessageRequest,
    context_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Use the established non-streaming generation boundary in the worker."""

    from .memory_commands import execute_memory_command, parse_memory_command

    command = parse_memory_command(user_message.content)
    if command is not None:
        memory_factory = getattr(chat_store, "memory_service_factory", None)
        if not callable(memory_factory):
            raise RuntimeError("Chat memory service is unavailable")
        result = execute_memory_command(
            chat_store,
            memory_factory(),
            session.id,
            user_message.id,
            command,
        )
        return {
            "content": result.content,
            "metadata": {
                "generation_status": "completed",
                "memory_command": result.model_dump(mode="json"),
            },
        }

    generate = getattr(chat_store, "_generate_reply", None)
    if not callable(generate):
        raise RuntimeError("Chat store does not provide a generation boundary")
    return generate(
        session,
        user_message,
        provider_id=request.provider_id or session.provider_id,
        model_id=request.model_id or session.model_id,
        request=request,
        context_items=context_items,
    )


def _persist_routing_metadata(
    chat_store: Any,
    session: ChatSession,
    user_message: ChatMessage,
) -> None:
    keys = (
        "omnix_chat_routed",
        "omnix_route",
        "semantic_intent",
        "semantic_task",
        "semantic_compilation",
        "routing_decision",
        "request_mode",
        "turn_plan",
        "active_objective",
        "routing_environment",
    )
    patch = {key: user_message.metadata[key] for key in keys if key in user_message.metadata}
    if not patch:
        return
    _patch_user_message_metadata(
        chat_store,
        session_id=session.id,
        message_id=user_message.id,
        metadata=patch,
    )


def _patch_user_message_metadata(
    chat_store: Any,
    *,
    session_id: str,
    message_id: str,
    metadata: dict[str, Any],
) -> None:
    if chat_store is None:
        return
    update = getattr(chat_store, "update_user_message_metadata", None)
    if callable(update):
        update(session_id=session_id, message_id=message_id, metadata=metadata)
        return
    sessions = chat_store._load_sessions()
    for index, session in enumerate(sessions):
        if session.id != session_id:
            continue
        for message in session.messages:
            if message.id == message_id:
                message.metadata.update(metadata)
                break
        sessions[index] = session
        chat_store._save_sessions(sessions)
        return


def _context_source_summaries(context_items: list[dict[str, Any]]) -> list[dict[str, str]]:
    summaries: list[dict[str, str]] = []
    for item in context_items:
        source_id = str(item.get("source_id") or "context").strip()
        title = str(item.get("title") or source_id).strip()
        summary = {"source_id": source_id, "title": title}
        url = str(item.get("url") or "").strip()
        if url:
            summary["url"] = url
        raw_metadata = item.get("metadata")
        item_metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        citation = str(item_metadata.get("citation_label") or "").strip()
        if citation:
            summary["citation"] = citation
        summaries.append(summary)
    return summaries
