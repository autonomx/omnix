from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from app.gateway.main import _live_job_event_stream, _parse_event_id, _sse_comment, _sse_event


@dataclass
class FakeJobEvent:
    id: int
    event_type: str
    payload: dict[str, Any]

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        assert mode == "json"
        return {"id": self.id, "event_type": self.event_type, **self.payload}


class FakeJobStore:
    def __init__(self, events: list[FakeJobEvent]):
        self._events = events
        self.after_ids: list[int] = []

    def list_events(self, after_id: int, limit: int):
        self.after_ids.append(after_id)
        return [event for event in self._events if event.id > after_id][:limit]


def test_sse_event_includes_optional_id_and_sorted_json_data():
    assert _sse_event("job.updated", {"z": 2, "a": 1}, event_id=42) == (
        'id: 42\n'
        'event: job.updated\n'
        'data: {"a": 1, "z": 2}\n\n'
    )


def test_sse_comment_and_event_id_parsing_are_tolerant():
    assert _sse_comment("heartbeat") == ": heartbeat\n\n"
    assert _parse_event_id("12") == 12
    assert _parse_event_id(None, fallback=7) == 7
    assert _parse_event_id("not-an-int", fallback=9) == 9


def test_live_job_event_stream_resumes_after_supplied_event_id():
    async def collect_first_three_chunks() -> tuple[list[str], list[int]]:
        store = FakeJobStore(
            [
                FakeJobEvent(id=1, event_type="job.created", payload={"job_id": "old"}),
                FakeJobEvent(id=2, event_type="job.updated", payload={"job_id": "current"}),
            ]
        )
        stream = _live_job_event_stream(store, after_id=1)
        try:
            chunks = [await anext(stream), await anext(stream), await anext(stream)]
        finally:
            await stream.aclose()
        return chunks, store.after_ids

    chunks, after_ids = asyncio.run(collect_first_three_chunks())

    assert chunks[0] == ": omnix-events-open\n\n"
    assert chunks[1] == (
        'id: 2\n'
        'event: job.updated\n'
        'data: {"event_type": "job.updated", "id": 2, "job_id": "current"}\n\n'
    )
    assert chunks[2] == ": heartbeat\n\n"
    assert after_ids[:2] == [1, 2]
