"""Context-local policy for staging RPG session writes into an outer transaction."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from typing import Any, Iterator


_DEFER_SESSION_SAVE: ContextVar[bool] = ContextVar(
    "omnix_rpg_defer_session_save",
    default=False,
)


def session_save_deferred() -> bool:
    """Return whether the current turn owns persistence through an outer unit of work."""

    return bool(_DEFER_SESSION_SAVE.get())


# While a turn defers its writes the saved game does not change, so the turn's
# stages, which each load it, can share one load (WP-5.6). Entries are keyed by
# the stored (revision, state_hash), checked on every read.
_TURN_LOADS: ContextVar[dict[str, tuple[tuple[int, str], dict[str, Any]]] | None] = ContextVar(
    "omnix_rpg_turn_session_loads",
    default=None,
)


@contextmanager
def rpg_session_save_policy(*, defer: bool) -> Iterator[None]:
    """Temporarily stage compatibility session saves for an atomic foreground turn."""

    token = _DEFER_SESSION_SAVE.set(bool(defer))
    loads = _TURN_LOADS.set({} if defer else None)
    try:
        yield
    finally:
        _TURN_LOADS.reset(loads)
        _DEFER_SESSION_SAVE.reset(token)


def cached_turn_load(session_id: str, version: tuple[int, str]) -> dict[str, Any] | None:
    """A copy of the session this turn already loaded at ``version``, if any."""
    loads = _TURN_LOADS.get()
    entry = loads.get(session_id) if loads is not None else None
    if entry is None or entry[0] != version:
        return None
    return deepcopy(entry[1])


def remember_turn_load(session_id: str, version: tuple[int, str], session: dict[str, Any]) -> None:
    """Keep a copy of a session loaded at ``version`` for this turn's later loads."""
    loads = _TURN_LOADS.get()
    if loads is not None:
        loads[session_id] = (version, deepcopy(session))
