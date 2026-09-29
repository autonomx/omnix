"""Resilient live job-event streaming for the runtime gateway."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from app.persistence.database import PostgresOperationError

EVENT_STREAM_BATCH_LIMIT = 100
EVENT_STREAM_POLL_SECONDS = 1.0
EVENT_STREAM_HEARTBEAT_SECONDS = 15.0


def _sse_event(event_type: str, payload: dict[str, Any], event_id: int | None = None) -> str:
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event_type}")
    lines.append(f"data: {json.dumps(payload, sort_keys=True)}")
    return "\n".join(lines) + "\n\n"


def _sse_comment(comment: str) -> str:
    return f": {comment}\n\n"


def _parse_event_id(value: str | None, fallback: int = 0) -> int:
    if not value:
        return fallback
    try:
        return max(0, int(value))
    except ValueError:
        return fallback


def latest_job_event_id(job_store: Any) -> int:
    """Return the current event tail without replaying the complete event table."""

    latest = getattr(job_store, "latest_event_id", None)
    if callable(latest):
        try:
            return max(0, int(latest()))
        except (TypeError, ValueError, PostgresOperationError, OSError):
            return 0
    return 0


def live_event_start_id(
    job_store: Any,
    *,
    after_id: int | None,
    last_event_id: str | None,
) -> int:
    """Resume explicit cursors, otherwise subscribe at the current event tail."""

    if last_event_id is not None:
        return _parse_event_id(last_event_id)
    if after_id is not None:
        return max(0, after_id)
    return latest_job_event_id(job_store)


async def resilient_live_job_event_stream(job_store: Any, after_id: int = 0):
    last_event_id = max(0, after_id)
    seconds_until_heartbeat = 0.0
    yield _sse_comment("omnix-events-open")
    while True:
        try:
            events = await asyncio.to_thread(job_store.list_events,
                after_id=last_event_id,
                limit=EVENT_STREAM_BATCH_LIMIT,
            )
        except (PostgresOperationError, OSError):
            yield _sse_comment("event-store-temporarily-unavailable")
            await asyncio.sleep(EVENT_STREAM_POLL_SECONDS)
            continue

        if events:
            for event in events:
                last_event_id = max(last_event_id, event.id)
                yield _sse_event(
                    event.event_type,
                    event.model_dump(mode="json"),
                    event_id=event.id,
                )
            seconds_until_heartbeat = 0.0
            continue

        if seconds_until_heartbeat <= 0:
            yield _sse_comment("heartbeat")
            seconds_until_heartbeat = EVENT_STREAM_HEARTBEAT_SECONDS
        await asyncio.sleep(EVENT_STREAM_POLL_SECONDS)
        seconds_until_heartbeat -= EVENT_STREAM_POLL_SECONDS
