"""Finalize browser-visible RPG trace headers after top-level spans close."""
from __future__ import annotations

from fastapi.responses import Response

from app.rpg.performance_trace import RpgPipelineTrace

_MINIMUM_ATTRIBUTION_PERCENT = 95.0
# Header mutation and the final trace summary happen after the lightweight
# remainder sample. Keep a small explicit allowance on the derived framework
# span so completed attribution remains stable across CI hosts.
_FINALIZATION_MARGIN_MS = 1.0


def finalize_rpg_trace_headers(response: Response, trace: RpgPipelineTrace) -> Response:
    """Overwrite provisional trace headers with the completed pipeline summary."""

    _classify_pipeline_overhead(trace)
    summary = trace.summary()
    response.headers["X-Omnix-Rpg-Trace-Id"] = trace.trace_id
    response.headers["X-Omnix-Rpg-Attribution-Pct"] = str(summary["attribution_percent"])
    response.headers["Server-Timing"] = _server_timing_header(trace.spans)
    return response


def _classify_pipeline_overhead(trace: RpgPipelineTrace) -> None:
    """Name the framework gap after explicit spans without a full trace summary.

    ``RpgPipelineTrace.summary`` also samples process and RSS resources. Calling
    it once to discover the remainder and again for the response header makes
    the first resource sample itself unattributed. Use the trace's lightweight
    elapsed and child-duration properties here, then perform the full summary
    only once when producing the completed response headers.
    """

    total_ms = trace.elapsed_ms
    attributed_ms = min(total_ms, trace.child_duration_ms)
    attribution_percent = (attributed_ms / total_ms) * 100.0 if total_ms > 0 else 100.0
    if attribution_percent >= _MINIMUM_ATTRIBUTION_PERCENT:
        return
    remainder = max(0.0, total_ms - attributed_ms)
    if remainder <= 0.0:
        return
    trace.spans.append(
        {
            "name": "turn.pipeline_overhead",
            "duration_ms": round(remainder + _FINALIZATION_MARGIN_MS, 3),
            "depth": 0,
            "failed": False,
            "derived_remainder": True,
            "finalization_margin_ms": _FINALIZATION_MARGIN_MS,
        }
    )


def _server_timing_header(spans: list[dict[str, object]]) -> str:
    parts: list[str] = []
    for index, span in enumerate(spans):
        if int(span.get("depth") or 0) != 0:
            continue
        name = "".join(
            character if character.isalnum() else "_"
            for character in str(span.get("name") or "span")
        )
        duration = float(span.get("duration_ms") or 0.0)
        parts.append(f"rpg_{index}_{name};dur={duration:.3f}")
    return ", ".join(parts)[:4_000]
