from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from app.rpg.session.narration_trace import record_narration_trace


_SUPPRESS_PROVIDER_RUNTIME_NARRATION: ContextVar[bool] = ContextVar(
    "RPG_SUPPRESS_PROVIDER_RUNTIME_NARRATION",
    default=False,
)


def suppress_provider_runtime_narration() -> bool:
    value = bool(_SUPPRESS_PROVIDER_RUNTIME_NARRATION.get())
    record_narration_trace("guard_check", suppress_provider_runtime_narration=value)
    return value


@contextmanager
def deferred_runtime_narration_context(enabled: bool = True) -> Iterator[None]:
    record_narration_trace("guard_enter", enabled=bool(enabled))
    token = _SUPPRESS_PROVIDER_RUNTIME_NARRATION.set(bool(enabled))
    try:
        yield
    finally:
        _SUPPRESS_PROVIDER_RUNTIME_NARRATION.reset(token)
        record_narration_trace("guard_exit", enabled=bool(enabled))