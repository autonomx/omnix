from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from typing import Any

from app.gateway.live_job_events import (
    install_resilient_live_job_events,
    live_event_start_id,
    resilient_live_job_event_stream,
)
from app.gateway.main import create_gateway_app


@dataclass
class FakeEvent:
    id: int
    event_type: str = "job.updated"

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        assert mode == "json"
        return {"id": self.id, "event_type": self.event_type, "payload": {"module": "image-generation"}}


class FakeStore:
    def __init__(self, events: list[FakeEvent] | None = None, *, fail_once: bool = False) -> None:
        self.events = events or []
        self.fail_once = fail_once

    def latest_event_id(self) -> int:
        return max((event.id for event in self.events), default=0)

    def list_events(self, after_id: int, limit: int):
        if self.fail_once:
            self.fail_once = False
            raise sqlite3.OperationalError("disk I/O error")
        return [event for event in self.events if event.id > after_id][:limit]


def test_live_event_default_starts_at_current_tail() -> None:
    store = FakeStore([FakeEvent(3), FakeEvent(9)])

    assert live_event_start_id(store, after_id=None, last_event_id=None) == 9
    assert live_event_start_id(store, after_id=2, last_event_id=None) == 2
    assert live_event_start_id(store, after_id=None, last_event_id="7") == 7


def test_live_event_stream_survives_transient_sqlite_error(monkeypatch) -> None:
    async def no_wait(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.gateway.live_job_events.asyncio.sleep", no_wait)

    async def collect() -> list[str]:
        stream = resilient_live_job_event_stream(FakeStore([FakeEvent(1)], fail_once=True))
        try:
            return [await anext(stream), await anext(stream), await anext(stream)]
        finally:
            await stream.aclose()

    chunks = asyncio.run(collect())

    assert chunks[0] == ": omnix-events-open\n\n"
    assert chunks[1] == ": event-store-temporarily-unavailable\n\n"
    assert "event: job.updated" in chunks[2]
    assert "id: 1" in chunks[2]


def test_runtime_installer_replaces_the_legacy_events_route() -> None:
    store = FakeStore()
    app = create_gateway_app(job_store_factory=lambda: store)

    install_resilient_live_job_events(app, job_store_factory=lambda: store)
    matching = [
        route
        for route in app.router.routes
        if getattr(route, "path", None) == "/events" and "GET" in getattr(route, "methods", set())
    ]

    assert len(matching) == 1
    assert matching[0].endpoint.__module__ == "app.gateway.live_job_events"
