"""Counting the model calls a turn makes (RQ-1.3; RQ-8.4 builds model cost per turn on it).

``counting_model_calls()`` opens a count for the work it encloses (a turn); every RPG model call inside it is
recorded by kind: ``provider`` for a call through RPG's provider access, ``narrative_writer`` for the narrative
engine's writer. The count is a ``Counter`` shared by reference, so calls made on worker threads started from
the enclosed work are counted too. Outside a count, recording does nothing.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_CALLS: ContextVar[Counter[str] | None] = ContextVar("rpg_model_calls", default=None)


@contextmanager
def counting_model_calls() -> Iterator[Counter[str]]:
    calls: Counter[str] = Counter()
    token = _CALLS.set(calls)
    try:
        yield calls
    finally:
        _CALLS.reset(token)


def current_model_calls() -> dict[str, int]:
    """The calls counted so far in the enclosing count, by kind (empty outside one)."""
    calls = _CALLS.get()
    return dict(sorted(calls.items())) if calls is not None else {}


def record_model_call(kind: str) -> None:
    calls = _CALLS.get()
    if calls is not None:
        calls[kind] += 1


class CountedProvider:
    """A provider whose calls are counted as ``provider`` calls; every other attribute is the provider's."""

    def __init__(self, provider: Any) -> None:
        self._provider = provider

    def __getattr__(self, name: str) -> Any:
        return getattr(self._provider, name)

    def chat_completion(self, *args: Any, **kwargs: Any) -> Any:
        record_model_call("provider")
        return self._provider.chat_completion(*args, **kwargs)

    def chat(self, *args: Any, **kwargs: Any) -> Any:
        record_model_call("provider")
        return self._provider.chat(*args, **kwargs)
