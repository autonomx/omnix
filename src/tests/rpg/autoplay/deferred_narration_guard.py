from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator


_SUPPRESS_PROVIDER_RUNTIME_NARRATION: ContextVar[bool] = ContextVar(
    "SUPPRESS_PROVIDER_RUNTIME_NARRATION",
    default=False,
)


def suppress_provider_runtime_narration() -> bool:
    return bool(_SUPPRESS_PROVIDER_RUNTIME_NARRATION.get())


@contextmanager
def deferred_runtime_narration_context(enabled: bool = True) -> Iterator[None]:
    token = _SUPPRESS_PROVIDER_RUNTIME_NARRATION.set(bool(enabled))
    try:
        yield
    finally:
        _SUPPRESS_PROVIDER_RUNTIME_NARRATION.reset(token)