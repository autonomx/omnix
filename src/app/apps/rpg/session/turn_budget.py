"""A per-user ceiling on RPG turns, which bounds the model calls play can spend (RQ-8.2).

Every turn makes at most a couple of model calls, so turns per hour bound a
player's model spend. The count is the caller's committed turns in the last
hour (PostgreSQL, so every gateway process sees the same count).
``OMNIX_RPG_TURNS_PER_HOUR`` sets the ceiling; 0 turns it off.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config.env import env_int

TURNS_PER_HOUR_ENV = "OMNIX_RPG_TURNS_PER_HOUR"
DEFAULT_TURNS_PER_HOUR = 600
WINDOW_SECONDS = 3600


class TurnBudgetExceeded(Exception):
    """The caller played the hour's turns; ``retry_after_seconds`` until the oldest one leaves the window."""

    def __init__(self, *, limit: int, used: int, retry_after_seconds: int) -> None:
        minutes = max(1, -(-retry_after_seconds // 60))
        super().__init__(
            f"You have played {used} turns in the last hour; the limit is {limit}. "
            f"You can play again in about {minutes} minute{'s' if minutes != 1 else ''}."
        )
        self.limit = limit
        self.used = used
        self.retry_after_seconds = retry_after_seconds


def turns_per_hour() -> int:
    return max(0, env_int(TURNS_PER_HOUR_ENV, DEFAULT_TURNS_PER_HOUR))


def _retry_after(oldest: Any, *, now: datetime) -> int:
    if not isinstance(oldest, datetime):
        return WINDOW_SECONDS
    if oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=timezone.utc)
    return max(1, int(WINDOW_SECONDS - (now - oldest).total_seconds()) + 1)


def require_turn_budget(*, now: datetime | None = None) -> None:
    """Raise ``TurnBudgetExceeded`` when the caller has no turn left this hour (PostgreSQL runtime only)."""
    limit = turns_per_hour()
    if limit <= 0:
        return
    from app.persistence.runtime import uses_postgresql_runtime

    if not uses_postgresql_runtime():
        return
    from app.apps.rpg.session.persistence.session_records import _context, _database
    from app.persistence.unit_of_work import unit_of_work

    database = _database()
    context = _context(database)
    with unit_of_work(database) as work:
        used, oldest = work.rpg.recent_turns_by_owner(context, window_seconds=WINDOW_SECONDS)
        work.rollback()
    if used >= limit:
        raise TurnBudgetExceeded(
            limit=limit,
            used=used,
            retry_after_seconds=_retry_after(oldest, now=now or datetime.now(timezone.utc)),
        )


__all__ = [
    "DEFAULT_TURNS_PER_HOUR",
    "TURNS_PER_HOUR_ENV",
    "TurnBudgetExceeded",
    "require_turn_budget",
    "turns_per_hour",
]
