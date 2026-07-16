"""Cooperative foreground-first scheduling for RPG LLM work."""
from __future__ import annotations

from contextlib import contextmanager
from threading import Condition
from typing import Iterator


class RpgLlmPriorityGate:
    """Serialize LLM work and stop background calls while a turn is waiting."""

    def __init__(self) -> None:
        self._condition = Condition()
        self._foreground_waiters = 0
        self._foreground_active = False
        self._background_active = False

    @contextmanager
    def foreground(self) -> Iterator[None]:
        with self._condition:
            self._foreground_waiters += 1
            try:
                while self._foreground_active or self._background_active:
                    self._condition.wait()
                self._foreground_active = True
            finally:
                self._foreground_waiters -= 1
        try:
            yield
        finally:
            with self._condition:
                self._foreground_active = False
                self._condition.notify_all()

    @contextmanager
    def background(self) -> Iterator[None]:
        with self._condition:
            while (
                self._foreground_active
                or self._foreground_waiters
                or self._background_active
            ):
                self._condition.wait()
            self._background_active = True
        try:
            yield
        finally:
            with self._condition:
                self._background_active = False
                self._condition.notify_all()

    def snapshot(self) -> dict[str, int | bool]:
        with self._condition:
            return {
                "foreground_waiters": self._foreground_waiters,
                "foreground_active": self._foreground_active,
                "background_active": self._background_active,
            }


RPG_LLM_PRIORITY_GATE = RpgLlmPriorityGate()


@contextmanager
def foreground_rpg_llm_priority() -> Iterator[None]:
    with RPG_LLM_PRIORITY_GATE.foreground():
        yield


@contextmanager
def background_rpg_llm_priority() -> Iterator[None]:
    with RPG_LLM_PRIORITY_GATE.background():
        yield
