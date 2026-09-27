"""Context-local policy for staging RPG session writes into an outer transaction."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator


_DEFER_SESSION_SAVE: ContextVar[bool] = ContextVar(
    "omnix_rpg_defer_session_save",
    default=False,
)


def session_save_deferred() -> bool:
    """Return whether the current turn owns persistence through an outer unit of work."""

    return bool(_DEFER_SESSION_SAVE.get())


@contextmanager
def rpg_session_save_policy(*, defer: bool) -> Iterator[None]:
    """Temporarily stage compatibility session saves for an atomic foreground turn."""

    token = _DEFER_SESSION_SAVE.set(bool(defer))
    try:
        yield
    finally:
        _DEFER_SESSION_SAVE.reset(token)
