"""One event reader per process: query rate and slow subscribers (WP-5.4)."""
from __future__ import annotations

import asyncio

from app.events.event_reader import SUBSCRIBER_QUEUE_SIZE, EventCursor, EventReader
from app.gateway.kernel_routes.live_event_stream import committed_event_stream
from app.runtime.tenant_context import local_tenant_context


def _event(index: int) -> dict:
    return {"tx_id": 1, "id": index, "job_id": "job", "event_type": "probe", "payload": {}, "created_at": "now"}


class _Reader(EventReader):
    """A reader whose database is a list of events."""

    def __init__(self, events: list[dict]) -> None:
        super().__init__(database=None, tenant=local_tenant_context())
        self.store = events

    def latest_cursor(self) -> EventCursor:
        return EventCursor(0, 0)

    def events_after(self, cursor: EventCursor, *, limit: int = 500) -> list[dict]:
        self.queries += 1
        return [event for event in self.store if EventCursor(event["tx_id"], event["id"]) > cursor][:limit]

    def _ensure_running(self) -> None:  # driven by poll_once in these tests
        return None


def test_subscriber_count_does_not_change_the_query_rate() -> None:
    async def scenario(subscribers: int) -> int:
        reader = _Reader([_event(index) for index in range(1, 4)])
        loop = asyncio.get_running_loop()
        for _ in range(subscribers):
            reader.subscribe(loop)
        for _ in range(10):
            reader.poll_once()
        return reader.queries

    assert asyncio.run(scenario(1)) == asyncio.run(scenario(100))


def test_a_subscriber_that_falls_behind_is_told_to_resync() -> None:
    async def scenario() -> list[str]:
        reader = _Reader([])
        stream = committed_event_stream(reader)
        chunks = [await stream.__anext__()]  # open comment; subscription exists
        subscription = next(iter(reader._subscribers))
        reader.store = [_event(index) for index in range(1, SUBSCRIBER_QUEUE_SIZE + 5)]
        reader.poll_once()
        await asyncio.sleep(0)  # let the offers land on the loop
        assert subscription.overflowed
        async for chunk in stream:
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(scenario())
    assert chunks[-1].startswith("event: resync")
    ids = [chunk.splitlines()[0] for chunk in chunks if chunk.startswith("id:")]
    assert len(ids) == len(set(ids))  # replayed events are not repeated from the queue


def test_stores_without_commit_order_read_the_id_part_of_a_cursor() -> None:
    from app.gateway.kernel_routes.live_event_stream import legacy_event_id

    assert legacy_event_id(None) is None
    assert legacy_event_id("42") == 42
    assert legacy_event_id("7:42") == 42
    assert legacy_event_id("garbage") == 0
