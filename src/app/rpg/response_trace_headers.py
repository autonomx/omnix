"""Finalize browser-visible RPG trace headers after top-level spans close."""
from __future__ import annotations

from fastapi.responses import Response

from app.rpg.performance_trace import RpgPipelineTrace


def finalize_rpg_trace_headers(response: Response, trace: RpgPipelineTrace) -> Response:
    """Overwrite provisional trace headers with the completed pipeline summary."""

    summary = trace.summary()
    response.headers["X-Omnix-Rpg-Trace-Id"] = trace.trace_id
    response.headers["X-Omnix-Rpg-Attribution-Pct"] = str(summary["attribution_percent"])
    response.headers["Server-Timing"] = _server_timing_header(trace.spans)
    return response


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
