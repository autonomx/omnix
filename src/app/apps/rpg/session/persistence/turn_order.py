"""A campaign's turns run one at a time, in the order they arrive (RQ-1.4, roadmap §4.1 "The submission queue").

Two tabs submitting at once used to plan both turns on the same revision, and the second commit was refused
(409). Now a turn waits for the campaign's turn in progress to finish, then runs on the state that turn left,
so both commit, in order. The wait is a PostgreSQL advisory lock on its own connection, so every gateway
process shares it; it holds no row and blocks no reader. A turn that waits longer than
``OMNIX_RPG_TURN_WAIT_SECONDS`` is refused as ``TurnInProgress``, which the player can retry.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from app.config.env import env_int

TURN_WAIT_ENV = "OMNIX_RPG_TURN_WAIT_SECONDS"
DEFAULT_TURN_WAIT_SECONDS = 120  # a turn with a slow model call takes tens of seconds


class TurnInProgress(Exception):
    """Another turn of the campaign is still running."""

    def __init__(self, session_id: str, waited_seconds: int) -> None:
        super().__init__("Another turn of this campaign is still running; try again in a moment.")
        self.session_id = session_id
        self.waited_seconds = waited_seconds


def turn_wait_seconds() -> int:
    return env_int(TURN_WAIT_ENV, DEFAULT_TURN_WAIT_SECONDS, minimum=1, maximum=3600)


@contextmanager
def campaign_turn(session_id: str) -> Iterator[None]:
    """Hold the campaign's turn for the block (PostgreSQL runtime; elsewhere turns are not shared)."""
    from app.persistence.runtime import uses_postgresql_runtime

    if not uses_postgresql_runtime():
        yield
        return
    import psycopg

    from app.apps.rpg.session.persistence.session_records import _context, _database

    database = _database()
    key = f"omnix:rpg:campaign-turn:{_context(database).workspace_id}:{session_id}"
    seconds = turn_wait_seconds()
    with database.dedicated_connection() as connection:
        try:
            connection.execute("SELECT set_config('lock_timeout', %s, false)", (f"{seconds}s",))
            connection.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", (key,))
            connection.commit()
        except psycopg.errors.LockNotAvailable as exc:
            raise TurnInProgress(session_id, seconds) from exc
        try:
            yield
        finally:
            connection.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (key,))
            connection.commit()


__all__ = ["DEFAULT_TURN_WAIT_SECONDS", "TURN_WAIT_ENV", "TurnInProgress", "campaign_turn", "turn_wait_seconds"]
