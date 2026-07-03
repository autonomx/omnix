"""Calendar runtime adapter foundation for assistant tools."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from .models import AssistantToolRequest, AssistantToolResult


@dataclass(frozen=True)
class CalendarEventRecord:
    id: str
    title: str
    start_time: str
    end_time: str
    attendees: tuple[str, ...] = ()
    location: str = ""


class CalendarRuntimeAdapter(Protocol):
    def read_availability(self, *, start_time: str, end_time: str) -> list[CalendarEventRecord]: ...

    def create_event(self, *, title: str, start_time: str, end_time: str, attendees: tuple[str, ...], location: str = "") -> CalendarEventRecord: ...


@dataclass
class FakeCalendarRuntimeAdapter:
    events: list[CalendarEventRecord] = field(default_factory=list)

    def read_availability(self, *, start_time: str, end_time: str) -> list[CalendarEventRecord]:
        return [event for event in self.events if event.start_time < end_time and event.end_time > start_time]

    def create_event(self, *, title: str, start_time: str, end_time: str, attendees: tuple[str, ...], location: str = "") -> CalendarEventRecord:
        event = CalendarEventRecord(
            id=f"event-{uuid.uuid4().hex[:12]}",
            title=title,
            start_time=start_time,
            end_time=end_time,
            attendees=attendees,
            location=location,
        )
        self.events.append(event)
        return event


def default_fake_calendar_adapter() -> FakeCalendarRuntimeAdapter:
    return FakeCalendarRuntimeAdapter(
        events=[
            CalendarEventRecord(
                id="event-1",
                title="Focus block",
                start_time="2026-07-03T09:00:00",
                end_time="2026-07-03T10:00:00",
            )
        ]
    )


_DEFAULT_CALENDAR_ADAPTER = default_fake_calendar_adapter()


def get_calendar_runtime_adapter() -> CalendarRuntimeAdapter:
    return _DEFAULT_CALENDAR_ADAPTER


def _as_attendees(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, list):
        return tuple(str(part).strip() for part in value if str(part).strip())
    return ()


def run_calendar_tool_request(request: AssistantToolRequest, adapter: CalendarRuntimeAdapter | None = None) -> AssistantToolResult:
    runtime = adapter or get_calendar_runtime_adapter()
    if request.action_id == "calendar.read_availability":
        start_time = str(request.input.get("start_time") or request.input.get("start") or "")
        end_time = str(request.input.get("end_time") or request.input.get("end") or "")
        events = runtime.read_availability(start_time=start_time, end_time=end_time)
        return AssistantToolResult(
            tool_id=request.tool_id,
            action_id=request.action_id,
            session_id=request.session_id,
            risk_level="low",
            state_changed=False,
            result_summary=f"Found {len(events)} calendar conflict{'s' if len(events) != 1 else ''}.",
            output={"events": [event.__dict__ for event in events]},
        )
    if request.action_id == "calendar.create_event":
        event = runtime.create_event(
            title=str(request.input.get("title") or "Untitled event"),
            start_time=str(request.input.get("start_time") or request.input.get("start") or ""),
            end_time=str(request.input.get("end_time") or request.input.get("end") or ""),
            attendees=_as_attendees(request.input.get("attendees") or []),
            location=str(request.input.get("location") or ""),
        )
        return AssistantToolResult(
            tool_id=request.tool_id,
            action_id=request.action_id,
            session_id=request.session_id,
            risk_level="medium",
            state_changed=True,
            result_summary=f"Created calendar event {event.id}: {event.title}.",
            output={"event": event.__dict__},
        )
    return AssistantToolResult(
        tool_id=request.tool_id,
        action_id=request.action_id,
        session_id=request.session_id,
        error="calendar_action_not_available",
    )
