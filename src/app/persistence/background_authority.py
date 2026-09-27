"""Fail closed on PostgreSQL operations from a supervised background worker."""

from contextlib import contextmanager
from contextvars import ContextVar

_OWNER = ContextVar("omnix_background_owner", default=None)


@contextmanager
def background_execution(owner):
    token = _OWNER.set(owner)
    try:
        owner.require_live()
        yield
    finally:
        _OWNER.reset(token)


def require_background_owner():
    owner = _OWNER.get()
    if owner is not None:
        owner.require_live()
