"""Cooperative, process-local priority at the shared TTS provider boundary."""
from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator, Literal
from uuid import uuid4

from app.persistence.blob_store import default_blob_root


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


def _lock(handle, *, blocking: bool) -> bool:
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
    except OSError:
        return False
    return True


def _unlock(handle) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _signal_dir() -> Path:
    return default_blob_root() / "tts-priority"


@contextmanager
def _priority_signal(priority: TtsPriority) -> Iterator[None]:
    if priority == "offline":
        yield
        return
    directory = _signal_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{priority}-{uuid4().hex}.lock"
    try:
        with path.open("w+b") as handle:
            handle.write(b"1")
            handle.flush()
            if not _lock(handle, blocking=True):
                raise OSError("could not hold TTS priority signal")
            try:
                yield
            finally:
                _unlock(handle)
    finally:
        path.unlink(missing_ok=True)


def other_process_priority_pending() -> bool:
    """Find active high-priority provider calls in other local processes."""
    directory = _signal_dir()
    if not directory.is_dir():
        return False
    for priority in ("realtime", "preview"):
        for path in directory.glob(f"{priority}-*.lock"):
            try:
                # A creator may have opened the file but not locked it yet.
                if time.time() - path.stat().st_mtime < 1:
                    return True
                with path.open("r+b") as handle:
                    if not _lock(handle, blocking=False):
                        return True
                    _unlock(handle)
                path.unlink(missing_ok=True)  # crashed owner left an unlocked marker
            except OSError:
                return True
    return False


@contextmanager
def generation_class(priority: TtsPriority) -> Iterator[None]:
    token = _CURRENT.set(priority)
    try:
        yield
    finally:
        _CURRENT.reset(token)


@contextmanager
def generation_slot() -> Iterator[None]:
    priority = _CURRENT.get()
    with _priority_signal(priority):
        with _GATE.slot(priority):
            yield
