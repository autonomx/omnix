"""Cooperative, process-local priority at the shared TTS provider boundary."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Literal


TtsPriority = Literal["realtime", "preview", "offline"]
_ORDER: tuple[TtsPriority, ...] = ("realtime", "preview", "offline")
_CURRENT: ContextVar[TtsPriority] = ContextVar("omnix_tts_priority", default="realtime")


class TtsGenerationGate:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._active = False
        self._waiting = {priority: 0 for priority in _ORDER}

    @contextmanager
    def slot(self, priority: TtsPriority) -> Iterator[None]:
        with self._condition:
            self._waiting[priority] += 1
            try:
                higher = _ORDER[:_ORDER.index(priority)]
                while self._active or any(self._waiting[item] for item in higher):
                    self._condition.wait()
                self._active = True
            finally:
                self._waiting[priority] -= 1
        try:
            yield
        finally:
            with self._condition:
                self._active = False
                self._condition.notify_all()

    def waiting(self, priority: TtsPriority) -> int:
        with self._condition:
            return self._waiting[priority]


_GATE = TtsGenerationGate()


@contextmanager
def generation_class(priority: TtsPriority) -> Iterator[None]:
    token = _CURRENT.set(priority)
    try:
        yield
    finally:
        _CURRENT.reset(token)


@contextmanager
def generation_slot() -> Iterator[None]:
    with _GATE.slot(_CURRENT.get()):
        yield
