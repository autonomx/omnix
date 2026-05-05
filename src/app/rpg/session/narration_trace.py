from __future__ import annotations

import time
import traceback
from contextvars import ContextVar
from typing import Any, Dict, List


_TRACE_ENABLED: ContextVar[bool] = ContextVar("RPG_NARRATION_TRACE_ENABLED", default=False)
_TRACE_ROWS: ContextVar[List[Dict[str, Any]] | None] = ContextVar("RPG_NARRATION_TRACE_ROWS", default=None)


def enable_narration_trace(enabled: bool = True) -> None:
    _TRACE_ENABLED.set(bool(enabled))
    if enabled and _TRACE_ROWS.get() is None:
        _TRACE_ROWS.set([])


def clear_narration_trace() -> None:
    _TRACE_ROWS.set([])


def narration_trace_enabled() -> bool:
    return bool(_TRACE_ENABLED.get())


def record_narration_trace(event: str, **fields: Any) -> None:
    if not narration_trace_enabled():
        return
    rows = _TRACE_ROWS.get()
    if rows is None:
        rows = []
        _TRACE_ROWS.set(rows)
    rows.append(
        {
            "event": event,
            "time": round(time.perf_counter(), 6),
            **fields,
        }
    )


def record_narration_trace_stack(event: str, **fields: Any) -> None:
    if not narration_trace_enabled():
        return
    stack = traceback.format_stack(limit=12)
    record_narration_trace(
        event,
        stack=[line.strip() for line in stack],
        **fields,
    )


def get_narration_trace() -> List[Dict[str, Any]]:
    rows = _TRACE_ROWS.get()
    return list(rows or [])