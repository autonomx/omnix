from __future__ import annotations

import os
import time
import traceback
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Iterator, List


_TURN_TRACE_ROWS: ContextVar[List[Dict[str, Any]] | None] = ContextVar(
    "RPG_SESSION_TURN_PERF_TRACE_ROWS",
    default=None,
)


def turn_perf_trace_enabled() -> bool:
    return os.getenv("RPG_TRACE_SESSION_TURN", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def clear_turn_perf_trace() -> None:
    _TURN_TRACE_ROWS.set([])


def get_turn_perf_trace() -> List[Dict[str, Any]]:
    return list(_TURN_TRACE_ROWS.get() or [])


def _rows() -> List[Dict[str, Any]]:
    rows = _TURN_TRACE_ROWS.get()
    if rows is None:
        rows = []
        _TURN_TRACE_ROWS.set(rows)
    return rows


def record_turn_perf_trace(event: str, **fields: Any) -> None:
    if not turn_perf_trace_enabled():
        return
    _rows().append(
        {
            "event": event,
            "time": round(time.perf_counter(), 6),
            **fields,
        }
    )


def record_turn_perf_trace_stack(event: str, **fields: Any) -> None:
    if not turn_perf_trace_enabled():
        return
    _rows().append(
        {
            "event": event,
            "time": round(time.perf_counter(), 6),
            "stack": [line.strip() for line in traceback.format_stack(limit=18)],
            **fields,
        }
    )


@contextmanager
def traced_turn_stage(event: str, **fields: Any) -> Iterator[None]:
    if not turn_perf_trace_enabled():
        yield
        return
    start = time.perf_counter()
    record_turn_perf_trace(f"{event}_enter", **fields)
    try:
        yield
    finally:
        record_turn_perf_trace(
            f"{event}_exit",
            elapsed_seconds=round(time.perf_counter() - start, 3),
            **fields,
        )


def summarize_turn_perf_trace(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    exits = [
        row for row in rows
        if isinstance(row, dict)
        and str(row.get("event") or "").endswith("_exit")
        and row.get("elapsed_seconds") is not None
    ]
    return {
        "stage_count": len(exits),
        "total_stage_seconds": round(
            sum(float(row.get("elapsed_seconds") or 0.0) for row in exits),
            3,
        ),
        "slowest_stages": sorted(
            [
                {
                    "event": row.get("event"),
                    "elapsed_seconds": row.get("elapsed_seconds"),
                }
                for row in exits
            ],
            key=lambda item: float(item.get("elapsed_seconds") or 0.0),
            reverse=True,
        )[:20],
        "events": [row.get("event") for row in rows if isinstance(row, dict)],
    }


def record_elapsed_turn_stage(stage: str, started: float, **fields: Any) -> None:
    record_turn_perf_trace(
        "runtime_core_stage_elapsed",
        stage=stage,
        elapsed_seconds=round(time.perf_counter() - started, 3),
        **fields,
    )