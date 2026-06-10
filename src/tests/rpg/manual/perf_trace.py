from __future__ import annotations

import os
import time
import traceback
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Iterator, List

_TRACE_ROWS: ContextVar[List[Dict[str, Any]] | None] = ContextVar(
    "RPG_MANUAL_HARNESS_PERF_TRACE_ROWS",
    default=None,
)


def manual_harness_trace_enabled() -> bool:
    return os.getenv("RPG_TRACE_MANUAL_HARNESS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def clear_manual_harness_trace() -> None:
    _TRACE_ROWS.set([])


def get_manual_harness_trace() -> List[Dict[str, Any]]:
    return list(_TRACE_ROWS.get() or [])


def _rows() -> List[Dict[str, Any]]:
    rows = _TRACE_ROWS.get()
    if rows is None:
        rows = []
        _TRACE_ROWS.set(rows)
    return rows


def record_manual_harness_trace(event: str, **fields: Any) -> None:
    if not manual_harness_trace_enabled():
        return
    _rows().append(
        {
            "event": event,
            "time": round(time.perf_counter(), 6),
            **fields,
        }
    )


def record_manual_harness_trace_stack(event: str, **fields: Any) -> None:
    if not manual_harness_trace_enabled():
        return
    _rows().append(
        {
            "event": event,
            "time": round(time.perf_counter(), 6),
            "stack": [line.strip() for line in traceback.format_stack(limit=16)],
            **fields,
        }
    )


@contextmanager
def traced_manual_stage(event: str, **fields: Any) -> Iterator[None]:
    if not manual_harness_trace_enabled():
        yield
        return

    start = time.perf_counter()
    record_manual_harness_trace(f"{event}_enter", **fields)
    try:
        yield
    except Exception as exc:
        record_manual_harness_trace(
            f"{event}_exception",
            exception_type=type(exc).__name__,
            exception_message=str(exc),
            traceback=traceback.format_exc(limit=80),
            **fields,
        )
        raise
    finally:
        elapsed = time.perf_counter() - start
        record_manual_harness_trace(
            f"{event}_exit",
            elapsed_seconds=round(elapsed, 3),
            **fields,
        )


def summarize_manual_harness_trace(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "stage_count": 0,
        "total_stage_seconds": 0.0,
        "slowest_stages": [],
        "events": [],
        "exceptions": [],
    }
    if not rows:
        return summary

    exits = [
        row for row in rows
        if isinstance(row, dict)
        and str(row.get("event") or "").endswith("_exit")
        and row.get("elapsed_seconds") is not None
    ]
    exceptions = [
        row for row in rows
        if isinstance(row, dict)
        and str(row.get("event") or "").endswith("_exception")
    ]
    summary["stage_count"] = len(exits)
    summary["total_stage_seconds"] = round(
        sum(float(row.get("elapsed_seconds") or 0.0) for row in exits),
        3,
    )
    summary["slowest_stages"] = sorted(
        [
            {
                "event": row.get("event"),
                "elapsed_seconds": row.get("elapsed_seconds"),
            }
            for row in exits
        ],
        key=lambda item: float(item.get("elapsed_seconds") or 0.0),
        reverse=True,
    )[:10]
    summary["events"] = [row.get("event") for row in rows if isinstance(row, dict)]
    summary["exceptions"] = [
        {
            "event": row.get("event"),
            "exception_type": row.get("exception_type"),
            "exception_message": row.get("exception_message"),
            "traceback": row.get("traceback"),
        }
        for row in exceptions
    ]
    return summary
