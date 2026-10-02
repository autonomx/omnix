"""Narration Worker — Manager and SSE pub/sub layer.

This module provides:
- Background worker lifecycle management
- Session pending-signal registry
- SSE subscriber registry for narration events
- Event publishing to SSE subscribers

It does NOT own any narration job queue.  The single authoritative
source of truth for narration jobs is the session runtime state
(runtime_state["narration_jobs"] / runtime_state["narration_jobs_by_turn"]).
Jobs are processed by ``process_next_narration_job(session_id)`` in
runtime.py.

Pending worker signals are a bounded process-local wakeup cache; job state
remains authoritative in session storage. Narration event delivery uses the
PostgreSQL event feed so an SSE connection can read events from any replica.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────

MAX_PENDING_SESSION_SIGNALS = 4096
PENDING_SESSION_SIGNAL_TTL_SECONDS = 60 * 60.0

# ── In-process state ──────────────────────────────────────────────────────

_worker_running = False
_worker_thread: Optional[threading.Thread] = None
_worker_lock = threading.Lock()
_pending_sessions: OrderedDict[str, float] = OrderedDict()
_pending_lock = threading.Lock()
_stop_requested = False

_WORKER_IDLE_SLEEP_SECONDS = 0.50
_WORKER_ACTIVE_SLEEP_SECONDS = 0.10
_MAX_SESSIONS_PER_WAKE = 8


# ── Worker lifecycle ──────────────────────────────────────────────────────

def ensure_narration_worker_running() -> None:
    """Ensure the narration worker manager is initialized.

    In the current single-process implementation this marks the worker
    as active.  A future multi-threaded implementation would start
    the background thread here.
    """
    global _worker_running, _worker_thread, _stop_requested
    with _worker_lock:
        if _worker_running and _worker_thread is not None and _worker_thread.is_alive():
            return
        _worker_running = True
        _stop_requested = False
        _worker_thread = threading.Thread(
            target=_worker_loop,
            name="rpg-narration-worker",
            daemon=True,
        )
        _worker_thread.start()


def request_narration_worker_stop() -> None:
    global _stop_requested
    with _worker_lock:
        _stop_requested = True


def signal_narration_work(session_id: Any) -> bool:
    """Signal that a session has pending narration work.

    Adds the *session_id* to the pending-signal registry so the
    background worker knows which sessions to poll via
    ``process_next_narration_job(session_id)``.

    Returns True if the session was registered for work.
    """
    session_id = str(session_id or "").strip()
    if not session_id:
        return False
    logger.info("Signaling narration work for session", extra={"session_id": session_id})
    with _pending_lock:
        now = time.monotonic()
        _prune_pending_sessions_locked(now)
        if session_id not in _pending_sessions and len(_pending_sessions) >= MAX_PENDING_SESSION_SIGNALS:
            logger.warning("Narration wakeup capacity reached", extra={"session_id": session_id})
            return False
        _pending_sessions[session_id] = now + PENDING_SESSION_SIGNAL_TTL_SECONDS
        _pending_sessions.move_to_end(session_id)
    return True


def drain_pending_sessions() -> list[str]:
    """Return and clear all session IDs that have pending work.

    Used by the worker loop to decide which sessions to process.
    """
    with _pending_lock:
        _prune_pending_sessions_locked(time.monotonic())
        sessions = list(_pending_sessions)[:_MAX_SESSIONS_PER_WAKE]
        for session_id in sessions:
            _pending_sessions.pop(session_id, None)
    return sessions


def clear_pending_session_signals() -> None:
    """Invalidate transient worker wakeups; queued narration remains in session storage."""

    with _pending_lock:
        _pending_sessions.clear()


def _prune_pending_sessions_locked(now: float) -> None:
    expired = [
        session_id
        for session_id, expires_at in _pending_sessions.items()
        if expires_at <= now
    ]
    for session_id in expired:
        _pending_sessions.pop(session_id, None)


# ── Internal worker loop ──────────────────────────────────────────────────

def _is_stop_requested() -> bool:
    with _worker_lock:
        return bool(_stop_requested)


def _worker_loop() -> None:
    # Import lazily to avoid circular imports at module import time.
    from app.rpg.session.narration_jobs import (
        process_next_narration_job as process_next_narration_job,
    )

    while True:
        if _is_stop_requested():
            return

        logger.debug("Narration worker loop iteration")
        session_ids = drain_pending_sessions()
        if session_ids:
            logger.info("Narration worker processing sessions", extra={"session_ids": session_ids, "count": len(session_ids)})
        else:
            logger.debug("Narration worker no pending sessions")
        if not session_ids:
            time.sleep(_WORKER_IDLE_SLEEP_SECONDS)
            continue

        processed_any = False
        for session_id in session_ids[:_MAX_SESSIONS_PER_WAKE]:
            if _is_stop_requested():
                return

            logger.info("Processing narration job for session", extra={"session_id": session_id})
            try:
                logger.debug("Calling process_next_narration_job for session", extra={"session_id": session_id})
                result = process_next_narration_job(session_id)
                logger.debug("process_next_narration_job returned", extra={"session_id": session_id, "result_keys": list(result.keys()) if isinstance(result, dict) else type(result)})
            except Exception:
                logger.exception("Narration worker failed while processing session %s", session_id)
                # Re-signal so the session is retried on a later wake.
                signal_narration_work(session_id)
                continue

            status = str((result or {}).get("status") or "").strip().lower()
            logger.info("Narration job processed", extra={"session_id": session_id, "status": status, "result": result})
            processed_any = True

            # Re-signal if there may still be queued work for this session.
            if status in {"completed", "failed", "stale"}:
                logger.debug("Re-signaling work for session due to status", extra={"session_id": session_id, "status": status})
                signal_narration_work(session_id)
            elif status not in {"idle", "claimed_elsewhere"}:
                logger.debug("Re-signaling work for session", extra={"session_id": session_id, "status": status})
                signal_narration_work(session_id)

        time.sleep(_WORKER_ACTIVE_SLEEP_SECONDS if processed_any else _WORKER_IDLE_SLEEP_SECONDS)


# ── Event publishing (SSE) ────────────────────────────────────────────────

def publish_narration_event(session_id: str, event: dict[str, Any]) -> int:
    """Append an event to PostgreSQL for delivery to SSE connections on any replica."""
    session_id = str(session_id or "")
    if not session_id:
        return 0
    from app.persistence.database import default_database
    from app.persistence.rpg_narration_event_repository import (
        PostgresRpgNarrationEventRepository,
    )

    try:
        with default_database().transaction() as connection:
            PostgresRpgNarrationEventRepository(connection).append(session_id, event)
    except Exception:
        logger.exception("Failed to persist RPG narration event")
        return 0
    return 1


def latest_narration_event_id(session_id: str) -> int:
    from app.persistence.database import default_database
    from app.persistence.rpg_narration_event_repository import (
        PostgresRpgNarrationEventRepository,
    )

    with default_database().transaction() as connection:
        return PostgresRpgNarrationEventRepository(connection).latest_event_id(session_id)


def list_narration_events_after(
    session_id: str,
    after_event_id: int,
    *,
    limit: int = 32,
) -> list[tuple[int, dict[str, Any]]]:
    from app.persistence.database import default_database
    from app.persistence.rpg_narration_event_repository import (
        PostgresRpgNarrationEventRepository,
    )

    with default_database().transaction() as connection:
        return PostgresRpgNarrationEventRepository(connection).list_after(
            session_id,
            after_event_id,
            limit=limit,
        )
