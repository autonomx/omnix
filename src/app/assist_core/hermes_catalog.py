from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .hermes_contract import HermesToolSpec


def hermes_catalog_specs() -> list[HermesToolSpec]:
    return [
        HermesToolSpec(
            name="calendar.read_availability",
            description="Read Google Calendar events in an exact ISO 8601 time range. Never invent missing dates or times.",
            risk="low",
            args_schema={"start_time": "ISO 8601 datetime", "end_time": "ISO 8601 datetime", "timezone": "IANA timezone"},
        ),
        HermesToolSpec(
            name="calendar.create_event",
            description=(
                "Propose a Google Calendar event or reminder. Requires an exact title, start_time, end_time, and timezone. "
                "If the user says an ambiguous time such as six without AM/PM or omits a date, do not invent it."
            ),
            risk="medium",
            args_schema={
                "title": "string",
                "start_time": "ISO 8601 datetime",
                "end_time": "ISO 8601 datetime",
                "timezone": "IANA timezone",
                "attendees": "list of email addresses",
                "location": "string",
                "description": "string",
                "reminder_minutes": "integer 0..40320",
            },
        ),
        HermesToolSpec(name="get_house_status", description="Read mock house status.", risk="low", args_schema={}),
        HermesToolSpec(name="get_hermes_status", description="Read Hermes status.", risk="low", args_schema={}),
        HermesToolSpec(name="get_hermes_diagnostics_schema", description="Read diagnostics schema.", risk="low", args_schema={}),
    ]


def hermes_catalog_payload() -> dict[str, Any]:
    return {"tools": [asdict(item) for item in hermes_catalog_specs()]}
