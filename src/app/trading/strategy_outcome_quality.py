"""Validity rules for timestamped shadow-trading outcomes."""

from __future__ import annotations

from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
_REGULAR_OPEN = time(9, 30)
_REGULAR_CLOSE = time(16, 0)


def regular_session_reference(at: datetime) -> bool:
    local = at.astimezone(_ET)
    return _REGULAR_OPEN <= local.time() <= _REGULAR_CLOSE


def episode_reference_is_valid(*, started_at: datetime, ended_at: datetime | None) -> bool:
    if started_at.tzinfo is None or not regular_session_reference(started_at):
        return False
    return (
        ended_at is None
        or (
            ended_at.tzinfo is not None
            and ended_at.astimezone(_ET).date() == started_at.astimezone(_ET).date()
        )
    )


def outcome_is_valid(row: dict[str, Any]) -> bool:
    value = row.get("started_at")
    try:
        started = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return False
    ended_value = row.get("ended_at")
    if ended_value is None:
        ended = None
    else:
        try:
            ended = (
                ended_value
                if isinstance(ended_value, datetime)
                else datetime.fromisoformat(str(ended_value))
            )
        except (TypeError, ValueError):
            return False
    return episode_reference_is_valid(started_at=started, ended_at=ended)


def outcome_is_valid_compat(row: dict[str, Any]) -> bool:
    """Keep pre-timestamp synthetic rows while validating known timestamps."""

    value = row.get("started_at")
    if value in {None, ""}:
        return True
    return outcome_is_valid(row)


__all__ = [
    "episode_reference_is_valid",
    "outcome_is_valid",
    "outcome_is_valid_compat",
    "regular_session_reference",
]
