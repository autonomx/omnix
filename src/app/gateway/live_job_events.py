"""Resilient live job-event streaming for the runtime gateway."""
from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Header, Query
from fastapi.responses import StreamingResponse

from app.jobs import InMemoryJobStore, default_job_store

EVENT_STREAM_BATCH_LIMIT = 100
EVENT_STREAM_POLL_SECONDS = 1.0
EVENT_STREAM_HEARTBEAT_SECONDS = 15.0
_ROUTE_SENTINEL = "_omnix_resilient_live_job_events_installed"


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
        except (TypeError, ValueError, sqlite3.Error, OSError):
            return 0

    connect = getattr(job_store, "_connect", None)
    if not callable(connect):
        return 0
    try:
        with connect() as conn:
            row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM job_events").fetchone()
        return max(0, int(row[0] if row else 0))
    except (TypeError, ValueError, sqlite3.Error, OSError):
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
            events = job_store.list_events(
                after_id=last_event_id,
                limit=EVENT_STREAM_BATCH_LIMIT,
            )
        except (sqlite3.Error, OSError):
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


def install_resilient_live_job_events(
    gateway: FastAPI,
    job_store_factory: Callable[[], InMemoryJobStore] | None = None,
) -> None:
    """Replace the legacy replay-from-zero stream with a tail-following stream."""

    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return
    setattr(gateway.state, _ROUTE_SENTINEL, True)

    gateway.router.routes = [
        route
        for route in gateway.router.routes
        if not (getattr(route, "path", None) == "/events" and "GET" in getattr(route, "methods", set()))
    ]
    get_job_store = job_store_factory or default_job_store

    @gateway.get("/events", include_in_schema=False)
    async def events(
        after_id: int | None = Query(default=None, ge=0),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        store = get_job_store()
        start_id = live_event_start_id(
            store,
            after_id=after_id,
            last_event_id=last_event_id,
        )
        return StreamingResponse(
            resilient_live_job_event_stream(store, after_id=start_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )
