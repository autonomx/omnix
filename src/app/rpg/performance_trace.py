"""End-to-end RPG request tracing with bounded structured stage metrics."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Iterator

from fastapi.responses import Response

from app.rpg.debug_logging import log_rpg_event, new_rpg_trace_id

_WARNING_THRESHOLD_ENV = "OMNIX_RPG_SLOW_SPAN_MS"
_DEFAULT_WARNING_THRESHOLD_MS = 500.0
_CURRENT_TRACE: ContextVar["RpgPipelineTrace | None"] = ContextVar("omnix_rpg_pipeline_trace", default=None)


@dataclass
class RpgPipelineTrace:
    trace_id: str
    operation: str
    session_id: str | None
    started_at: float = field(default_factory=perf_counter)
    spans: list[dict[str, Any]] = field(default_factory=list)
    fields: dict[str, Any] = field(default_factory=dict)

    @property
    def elapsed_ms(self) -> float:
        return round((perf_counter() - self.started_at) * 1000.0, 3)

    @property
    def child_duration_ms(self) -> float:
        return round(sum(float(span.get("duration_ms") or 0.0) for span in self.spans), 3)

    def summary(self) -> dict[str, Any]:
        total_ms = self.elapsed_ms
        child_ms = self.child_duration_ms
        return {
            "operation": self.operation,
            "trace_id": self.trace_id,
            "total_ms": total_ms,
            "child_duration_ms": child_ms,
            "unattributed_ms": round(max(0.0, total_ms - child_ms), 3),
            "span_count": len(self.spans),
            "spans": list(self.spans),
            **self.fields,
        }


def current_rpg_pipeline_trace() -> RpgPipelineTrace | None:
    return _CURRENT_TRACE.get()


@contextmanager
def rpg_pipeline_trace(
    operation: str,
    *,
    session_id: str | None = None,
    trace_id: str | None = None,
    fields: dict[str, Any] | None = None,
) -> Iterator[RpgPipelineTrace]:
    trace = RpgPipelineTrace(
        trace_id=trace_id or new_rpg_trace_id("pipeline"),
        operation=str(operation or "rpg.pipeline"),
        session_id=str(session_id) if session_id else None,
        fields=dict(fields or {}),
    )
    token = _CURRENT_TRACE.set(trace)
    log_rpg_event(
        f"{trace.operation}.started",
        category="performance",
        session_id=trace.session_id,
        trace_id=trace.trace_id,
        fields=trace.fields,
    )
    try:
        yield trace
    except Exception as exc:
        log_rpg_event(
            f"{trace.operation}.failed",
            category="performance",
            level="error",
            session_id=trace.session_id,
            trace_id=trace.trace_id,
            duration_ms=trace.elapsed_ms,
            fields=trace.summary(),
            error=exc,
            include_traceback=True,
        )
        raise
    else:
        log_rpg_event(
            f"{trace.operation}.completed",
            category="performance",
            session_id=trace.session_id,
            trace_id=trace.trace_id,
            duration_ms=trace.elapsed_ms,
            fields=trace.summary(),
        )
    finally:
        _CURRENT_TRACE.reset(token)


@contextmanager
def rpg_pipeline_span(
    name: str,
    *,
    fields: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    trace = current_rpg_pipeline_trace()
    started_at = perf_counter()
    mutable_fields = dict(fields or {})
    try:
        yield mutable_fields
    except Exception as exc:
        duration_ms = (perf_counter() - started_at) * 1000.0
        _record_span(trace, name, duration_ms, mutable_fields, failed=True)
        log_rpg_event(
            f"{name}.failed",
            category="performance",
            level="error",
            session_id=trace.session_id if trace else None,
            trace_id=trace.trace_id if trace else None,
            duration_ms=duration_ms,
            fields=mutable_fields,
            error=exc,
            include_traceback=True,
        )
        raise
    else:
        duration_ms = (perf_counter() - started_at) * 1000.0
        level = "warning" if duration_ms >= slow_span_threshold_ms() else "info"
        _record_span(trace, name, duration_ms, mutable_fields, failed=False)
        log_rpg_event(
            f"{name}.completed",
            category="performance",
            level=level,
            session_id=trace.session_id if trace else None,
            trace_id=trace.trace_id if trace else None,
            duration_ms=duration_ms,
            fields=mutable_fields,
        )


def build_traced_json_response(payload: dict[str, Any], *, status_code: int = 200) -> Response:
    if payload.get("contract_version") == "rpg_turn_response_v2":
        from app.rpg.presentation.turn_response import TURN_RESPONSE_MAX_BYTES
        from app.rpg.presentation.turn_response_budget import enforce_turn_response_budget

        payload = enforce_turn_response_budget(
            payload,
            max_bytes=TURN_RESPONSE_MAX_BYTES,
        )
    with rpg_pipeline_span("turn.response_json_encode") as span:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        budget = payload.get("response_budget") if isinstance(payload.get("response_budget"), dict) else {}
        span["response_bytes"] = len(encoded)
        span["contract_version"] = payload.get("contract_version")
        span["response_compacted"] = budget.get("compacted") is True
        span["response_fallback"] = budget.get("fallback") is True
    trace = current_rpg_pipeline_trace()
    if trace is not None:
        trace.fields["response_bytes"] = len(encoded)
        trace.fields["response_contract_version"] = payload.get("contract_version")
        trace.fields["response_compacted"] = budget.get("compacted") is True
    return Response(content=encoded, status_code=status_code, media_type="application/json")


def slow_span_threshold_ms() -> float:
    try:
        return max(0.0, float(os.getenv(_WARNING_THRESHOLD_ENV, str(_DEFAULT_WARNING_THRESHOLD_MS))))
    except (TypeError, ValueError):
        return _DEFAULT_WARNING_THRESHOLD_MS


def _record_span(
    trace: RpgPipelineTrace | None,
    name: str,
    duration_ms: float,
    fields: dict[str, Any],
    *,
    failed: bool,
) -> None:
    if trace is None:
        return
    trace.spans.append(
        {
            "name": str(name),
            "duration_ms": round(float(duration_ms), 3),
            "failed": bool(failed),
            **fields,
        }
    )
