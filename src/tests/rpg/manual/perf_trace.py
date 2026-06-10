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
_MAX_TRACEBACK_CHARS = 12000


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


def _truncate_text(value: object, *, limit: int = _MAX_TRACEBACK_CHARS) -> str:
    try:
        text = "" if value is None else str(value)
    except Exception as exc:  # pragma: no cover - defensive only
        text = f"<{type(exc).__name__}>"
    return text if len(text) <= limit else text[-limit:]


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
    had_exception = False
    record_manual_harness_trace(f"{event}_enter", **fields)
    try:
        yield
    except Exception as exc:
        had_exception = True
        record_manual_harness_trace(
            f"{event}_exception",
            error_type=type(exc).__name__,
            error_message=_truncate_text(exc, limit=2000),
            traceback=_truncate_text(traceback.format_exc()),
            **fields,
        )
        raise
    finally:
        elapsed = time.perf_counter() - start
        record_manual_harness_trace(
            f"{event}_exit",
            elapsed_seconds=round(elapsed, 3),
            had_exception=had_exception,
            **fields,
        )


def summarize_manual_harness_trace(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "stage_count": 0,
        "total_stage_seconds": 0.0,
        "slowest_stages": [],
        "events": [],
        "exception_events": [],
    }
    if not rows:
        return summary

    exits = [
        row for row in rows
        if isinstance(row, dict)
        and str(row.get("event") or "").endswith("_exit")
        and row.get("elapsed_seconds") is not None
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
                "had_exception": bool(row.get("had_exception")),
            }
            for row in exits
        ],
        key=lambda item: float(item.get("elapsed_seconds") or 0.0),
        reverse=True,
    )[:10]
    summary["events"] = [row.get("event") for row in rows if isinstance(row, dict)]
    summary["exception_events"] = [
        {
            "event": row.get("event"),
            "error_type": row.get("error_type"),
            "error_message": row.get("error_message"),
            "traceback": row.get("traceback"),
        }
        for row in rows
        if isinstance(row, dict) and str(row.get("event") or "").endswith("_exception")
    ][:20]
    return summary
