from __future__ import annotations

import time
from datetime import datetime
from zoneinfo import ZoneInfo

from app.assistant_memory.models import MemoryRecord, MemoryScopeContext
from app.assistant_memory.temporal_retrieval import (
    invalidate_temporal_retrieval,
    rank_temporal_records,
    retrieve_temporal_context,
)


def _record(
    memory_id: str,
    *,
    kind: str,
    content: str,
    payload: dict,
    category: str = "fact",
) -> MemoryRecord:
    return MemoryRecord(
        id=memory_id,
        owner_type="character",
        owner_id="character:maya",
        scope="global",
        scope_id="profile:default",
        category=category,
        kind=kind,
        structured_payload=payload,
        source="user_saved",
        content=content,
        normalized_content=content.casefold(),
        confidence=0.9,
        pinned=False,
        trust_level="user_approved",
        sensitivity="normal",
        provenance_type="user_message",
        provenance_id="message:1",
        status="active",
        revision=1,
        created_at="2026-07-01T00:00:00+00:00",
        updated_at="2026-07-01T00:00:00+00:00",
    )


def _context() -> MemoryScopeContext:
    return MemoryScopeContext(
        profile_id="profile:default",
        workspace_id="workspace:local",
        project_id=None,
        session_id="chat:temporal",
        owner_type="character",
        owner_id="character:maya",
    )


def test_weekday_commute_activates_near_seven_from_hello() -> None:
    route = _record(
        "memory:route-x",
        kind="routine",
        content="The user usually takes Route X to work.",
        payload={
            "activity": "commute_to_work",
            "days": ["MO", "TU", "WE", "TH", "FR"],
            "start_time": "07:00",
            "timezone": "America/Vancouver",
            "evidence_count": 4,
        },
    )
    now = datetime(2026, 7, 20, 7, 5, tzinfo=ZoneInfo("America/Vancouver"))

    selected = rank_temporal_records(
        [route],
        "hello",
        now=now,
        timezone_name="America/Vancouver",
    )

    assert [item.memory_id for item in selected] == ["memory:route-x"]
    assert "routine_start_window" in selected[0].reasons


def test_commute_does_not_activate_outside_window_or_on_weekend() -> None:
    route = _record(
        "memory:route-x",
        kind="routine",
        content="The user usually takes Route X to work.",
        payload={
            "activity": "commute_to_work",
            "days": ["MO", "TU", "WE", "TH", "FR"],
            "start_time": "07:00",
            "evidence_count": 4,
        },
    )
    zone = ZoneInfo("America/Vancouver")

    assert rank_temporal_records(
        [route], "hello", now=datetime(2026, 7, 20, 10, 0, tzinfo=zone), timezone_name=zone.key
    ) == ()
    assert rank_temporal_records(
        [route], "hello", now=datetime(2026, 7, 19, 7, 0, tzinfo=zone), timezone_name=zone.key
    ) == ()


def test_routine_exact_date_and_date_range_exceptions_suppress_activation() -> None:
    route = _record(
        "memory:route-x",
        kind="routine",
        content="The user usually takes Route X to work.",
        payload={
            "activity": "commute_to_work",
            "days": ["MO", "TU", "WE", "TH", "FR"],
            "start_time": "07:00",
            "exceptions": ["2026-07-20", "2026-07-27/2026-07-31"],
        },
    )
    zone = ZoneInfo("America/Vancouver")

    assert rank_temporal_records(
        [route], "hello", now=datetime(2026, 7, 20, 7, 0, tzinfo=zone), timezone_name=zone.key
    ) == ()
    assert rank_temporal_records(
        [route], "hello", now=datetime(2026, 7, 29, 7, 0, tzinfo=zone), timezone_name=zone.key
    ) == ()
    selected = rank_temporal_records(
        [route], "hello", now=datetime(2026, 7, 21, 7, 0, tzinfo=zone), timezone_name=zone.key
    )
    assert [item.memory_id for item in selected] == ["memory:route-x"]


def test_timezone_and_dst_use_local_wall_clock() -> None:
    route = _record(
        "memory:route-x",
        kind="routine",
        content="The user usually takes Route X to work.",
        payload={
            "activity": "commute_to_work",
            "days": ["MO", "TU", "WE", "TH", "FR"],
            "start_time": "07:00",
        },
    )
    zone = ZoneInfo("America/Vancouver")
    winter = datetime(2026, 1, 5, 7, 0, tzinfo=zone)
    summer = datetime(2026, 7, 20, 7, 0, tzinfo=zone)

    assert rank_temporal_records([route], "hello", now=winter, timezone_name=zone.key)
    assert rank_temporal_records([route], "hello", now=summer, timezone_name=zone.key)


def test_preload_deadline_falls_back_and_warms_cache() -> None:
    invalidate_temporal_retrieval()
    route = _record(
        "memory:route-x",
        kind="routine",
        content="The user usually takes Route X to work.",
        payload={"activity": "commute", "days": ["MO"], "start_time": "07:00"},
    )

    class SlowService:
        def list_active(self, context):
            del context
            time.sleep(0.05)
            return [route]

    now = datetime(2026, 7, 20, 7, 0, tzinfo=ZoneInfo("America/Vancouver"))
    first = retrieve_temporal_context(
        SlowService(),
        _context(),
        "hello",
        now=now,
        timezone_name="America/Vancouver",
        deadline_ms=1,
    )
    assert first.preload_timed_out is True
    assert first.items == ()

    time.sleep(0.08)
    second = retrieve_temporal_context(
        SlowService(),
        _context(),
        "hello",
        now=now,
        timezone_name="America/Vancouver",
        deadline_ms=1,
    )
    assert second.preload_cache_hit is True
    assert second.preload_timed_out is False
    assert [item.memory_id for item in second.items] == ["memory:route-x"]
