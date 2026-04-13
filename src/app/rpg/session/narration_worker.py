"""Narration Worker — In-process narration job queue and worker.

Provides a simple, bounded, in-process queue for narration jobs.
Jobs are enqueued by the idle tick and turn systems, and processed
synchronously or asynchronously depending on context.

This module exists primarily to satisfy the import contract expected
by runtime.py and rpg_session_routes.py.

Note: Module-level state is designed for single-process use.
In a multi-threaded environment, the queue.Queue is thread-safe,
but the subscriber dict is not. For multi-process deployments,
replace with an external message broker.
"""
from __future__ import annotations

import asyncio
import logging
import queue
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────

_MAX_QUEUE_SIZE = 64
_MAX_SUBSCRIBERS = 16

# ── In-process state ──────────────────────────────────────────────────────

_narration_queue: queue.Queue = queue.Queue(maxsize=_MAX_QUEUE_SIZE)
_worker_running = False
_subscribers: Dict[str, List[asyncio.Queue]] = {}


# ── Queue operations ──────────────────────────────────────────────────────

def signal_narration_work(job: Optional[Dict[str, Any]] = None) -> bool:
    """Enqueue a narration job for processing.

    If the queue is full, the oldest item is discarded.
    Returns True if the job was enqueued.
    """
    if job is None:
        return False
    try:
        _narration_queue.put_nowait(dict(job))
        return True
    except queue.Full:
        # Discard oldest and retry
        try:
            _narration_queue.get_nowait()
        except queue.Empty:
            pass
        try:
            _narration_queue.put_nowait(dict(job))
            return True
        except queue.Full:
            return False


def ensure_narration_worker_running() -> None:
    """Ensure the narration worker is initialized.

    In the current implementation this is a no-op since jobs are
    processed synchronously during idle ticks.  The function exists
    to satisfy the import contract.
    """
    global _worker_running
    _worker_running = True


# ── Event publishing (SSE) ────────────────────────────────────────────────

def publish_narration_event(session_id: str, event: Dict[str, Any]) -> int:
    """Publish a narration event to all subscribers for a session.

    Returns the number of subscribers that received the event.
    """
    session_id = str(session_id or "")
    if not session_id:
        return 0

    subscribers = _subscribers.get(session_id, [])
    delivered = 0
    for q in subscribers:
        try:
            q.put_nowait(dict(event))
            delivered += 1
        except (asyncio.QueueFull, Exception):
            pass
    return delivered


def subscribe_narration_events(session_id: str) -> asyncio.Queue:
    """Create a new subscriber queue for narration events.

    Returns an asyncio.Queue that will receive events.
    """
    session_id = str(session_id or "")
    if session_id not in _subscribers:
        _subscribers[session_id] = []

    # Trim old subscribers to prevent unbounded growth
    if len(_subscribers[session_id]) >= _MAX_SUBSCRIBERS:
        _subscribers[session_id] = _subscribers[session_id][-(_MAX_SUBSCRIBERS - 1):]

    subscriber_q: asyncio.Queue = asyncio.Queue(maxsize=_MAX_QUEUE_SIZE)
    _subscribers[session_id].append(subscriber_q)
    return subscriber_q


def unsubscribe_narration_events(session_id: str, subscriber_q: asyncio.Queue) -> None:
    """Remove a subscriber queue from the session's subscriber list."""
    session_id = str(session_id or "")
    subs = _subscribers.get(session_id, [])
    _subscribers[session_id] = [q for q in subs if q is not subscriber_q]
    if not _subscribers[session_id]:
        _subscribers.pop(session_id, None)


# ── Job processing ────────────────────────────────────────────────────────

def get_pending_jobs(limit: int = 8) -> List[Dict[str, Any]]:
    """Drain up to ``limit`` pending jobs from the queue."""
    jobs: List[Dict[str, Any]] = []
    for _ in range(min(limit, _MAX_QUEUE_SIZE)):
        try:
            job = _narration_queue.get_nowait()
            if isinstance(job, dict):
                jobs.append(job)
        except queue.Empty:
            break
    return jobs


def get_queue_size() -> int:
    """Return the approximate number of pending jobs."""
    return _narration_queue.qsize()


def clear_queue() -> int:
    """Clear all pending jobs. Returns the number cleared."""
    cleared = 0
    while True:
        try:
            _narration_queue.get_nowait()
            cleared += 1
        except queue.Empty:
            break
    return cleared
