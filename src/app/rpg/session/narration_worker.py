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

Note: Module-level state is designed for single-process use.
In a multi-process deployment, replace the subscriber dict with an
external message broker.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────

_MAX_SUBSCRIBER_QUEUE_SIZE = 64
_MAX_SUBSCRIBERS_PER_SESSION = 16

# ── In-process state ──────────────────────────────────────────────────────

_worker_running = False
_worker_lock = threading.Lock()
_pending_sessions: Set[str] = set()
_pending_lock = threading.Lock()
_subscribers: Dict[str, List[asyncio.Queue]] = {}


# ── Worker lifecycle ──────────────────────────────────────────────────────

def ensure_narration_worker_running() -> None:
    """Ensure the narration worker manager is initialized.

    In the current single-process implementation this marks the worker
    as active.  A future multi-threaded implementation would start
    the background thread here.
    """
    global _worker_running
    with _worker_lock:
        _worker_running = True


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
    with _pending_lock:
        _pending_sessions.add(session_id)
    return True


def drain_pending_sessions() -> List[str]:
    """Return and clear all session IDs that have pending work.

    Used by the worker loop to decide which sessions to process.
    """
    with _pending_lock:
        sessions = sorted(_pending_sessions)
        _pending_sessions.clear()
    return sessions


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
    if len(_subscribers[session_id]) >= _MAX_SUBSCRIBERS_PER_SESSION:
        _subscribers[session_id] = _subscribers[session_id][-(_MAX_SUBSCRIBERS_PER_SESSION - 1):]

    subscriber_q: asyncio.Queue = asyncio.Queue(maxsize=_MAX_SUBSCRIBER_QUEUE_SIZE)
    _subscribers[session_id].append(subscriber_q)
    return subscriber_q


def unsubscribe_narration_events(session_id: str, subscriber_q: asyncio.Queue) -> None:
    """Remove a subscriber queue from the session's subscriber list."""
    session_id = str(session_id or "")
    subs = _subscribers.get(session_id, [])
    _subscribers[session_id] = [q for q in subs if q is not subscriber_q]
    if not _subscribers[session_id]:
        _subscribers.pop(session_id, None)
