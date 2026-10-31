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
# A call made for something the turn may not use (a reply written beside the intent call, EV-9) is counted apart.
_AS: ContextVar[str] = ContextVar("rpg_model_call_kind", default="")
APART = "parallel_reply"


@contextmanager
def counting_model_calls() -> Iterator[Counter[str]]:
    calls: Counter[str] = Counter()
    token = _CALLS.set(calls)
    try:
        yield calls
    finally:
        _CALLS.reset(token)


_FAILED = "failed:"


def current_model_calls() -> dict[str, int]:
    """The calls counted so far in the enclosing count, by kind (empty outside one)."""
    calls = _CALLS.get()
    return dict(sorted((kind, count) for kind, count in calls.items() if not kind.startswith(_FAILED))) if calls else {}


def current_model_failures() -> dict[str, int]:
    """The calls that failed so far in the enclosing count (the provider down or too slow), by kind (RQ-8.8)."""
    calls = _CALLS.get()
    return {kind.removeprefix(_FAILED): count for kind, count in sorted(calls.items())
            if kind.startswith(_FAILED)} if calls else {}


def record_model_call(kind: str) -> None:
    calls = _CALLS.get()
    if calls is not None:
        calls[_AS.get() or kind] += 1


@contextmanager
def counted_as(kind: str) -> Iterator[None]:
    """Count the calls the enclosed work makes as ``kind`` (``APART``: not the turn's own, unless it uses them)."""
    token = _AS.set(kind)
    try:
        yield
    finally:
        _AS.reset(token)


def used_apart(kind: str = "provider") -> None:
    """A call counted apart that the turn used after all: counted as the turn's own ``kind``."""
    calls = _CALLS.get()
    if calls is not None and calls.get(APART):
        calls[APART] -= 1
        calls[kind] += 1


def used_calls(calls: dict[str, int]) -> int:
    """The calls whose output the turn used (F3): every call but those counted apart."""
    return sum(count for kind, count in calls.items() if kind != APART)


def record_model_failure(kind: str) -> None:
    calls = _CALLS.get()
    if calls is not None:
        calls[_FAILED + kind] += 1


class CountedProvider:
    """A provider whose calls are counted as ``provider`` calls; every other attribute is the provider's."""

    def __init__(self, provider: Any) -> None:
        self._provider = provider

    def __getattr__(self, name: str) -> Any:
        return getattr(self._provider, name)

    def chat_completion(self, *args: Any, **kwargs: Any) -> Any:
        record_model_call("provider")
        try:
            return self._provider.chat_completion(*args, **kwargs)
        except Exception:
            record_model_failure("provider")
            raise

    def chat(self, *args: Any, **kwargs: Any) -> Any:
        record_model_call("provider")
        try:
            return self._provider.chat(*args, **kwargs)
        except Exception:
            record_model_failure("provider")
            raise
