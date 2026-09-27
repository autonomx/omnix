"""Explicit, thread-confined connection sharing for one application operation."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import threading
from typing import Any


@dataclass(frozen=True)
class TransactionBinding:
    work: Any
    thread_id: int


_BINDING: ContextVar[TransactionBinding | None] = ContextVar(
    "omnix_shared_transaction", default=None
)


def shared_work(database):
    binding = _BINDING.get()
    if binding is None:
        return None
    if binding.thread_id != threading.get_ident():
        raise RuntimeError("A shared PostgreSQL transaction cannot cross threads")
    if binding.work.database is not database:
        raise RuntimeError(
            "An atomic operation cannot use a different database adapter"
        )
    binding.work._require_connection()
    return binding.work


@contextmanager
def share_transaction(work):
    work._require_connection()
    token = _BINDING.set(TransactionBinding(work, threading.get_ident()))
    try:
        yield
    finally:
        _BINDING.reset(token)


def after_commit(database, callback):
    work = shared_work(database)
    if work is None:
        callback()
    else:
        work._after_commit.append(callback)
