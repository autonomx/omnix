"""Prometheus metrics for the gateway (WP-10.3).

The registry is built on first use, not at import: ``prometheus_client``
imports 28 modules, and composing the gateway records nothing. The catalog is
documented in ``docs/operations/METRICS.md``. Labels stay bounded: routes are
templates (``/api/chat/sessions/{session_id}``), never raw paths, and statuses
are classes (``2xx`` ... ``5xx``).
"""
from __future__ import annotations

import threading
import time
from typing import Any

_UNMATCHED_ROUTE = "unmatched"
_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)
_lock = threading.Lock()
_metrics: dict[str, Any] | None = None


def _build() -> dict[str, Any]:
    from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

    registry = CollectorRegistry()
    return {
        "registry": registry,
        "requests": Counter(
            "omnix_http_requests", "HTTP requests by route template, method and status class.",
            ("route", "method", "status_class"), registry=registry,
        ),
        "latency": Histogram(
            "omnix_http_request_duration_seconds", "HTTP request duration by route template and method.",
            ("route", "method"), buckets=_LATENCY_BUCKETS, registry=registry,
        ),
        "in_flight": Gauge("omnix_http_requests_in_flight", "HTTP requests being handled.", registry=registry),
    }


def _get() -> dict[str, Any]:
    global _metrics
    if _metrics is None:
        with _lock:
            if _metrics is None:
                _metrics = _build()
    return _metrics


def route_template(scope: dict[str, Any]) -> str:
    """The matched route's template; requests no route matched share one label."""
    return str(getattr(scope.get("route"), "path", "") or _UNMATCHED_ROUTE)


def status_class(status: int) -> str:
    return f"{min(max(status // 100, 1), 5)}xx"


class HttpMetricsMiddleware:
    """Count, time and track in-flight HTTP requests (pure ASGI, streaming-safe)."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        metrics = _get()
        status = 500
        started = time.perf_counter()

        async def send_with_status(message: dict[str, Any]) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        metrics["in_flight"].inc()
        try:
            await self.app(scope, receive, send_with_status)
        finally:
            metrics["in_flight"].dec()
            route, method = route_template(scope), str(scope.get("method", ""))
            metrics["requests"].labels(route, method, status_class(status)).inc()
            metrics["latency"].labels(route, method).observe(time.perf_counter() - started)


def request_snapshot() -> dict[str, int]:
    """Totals for the diagnostics payload: in flight, handled and 5xx."""
    metrics = _get()
    handled = errors = 0.0
    for family in metrics["requests"].collect():
        for sample in family.samples:
            if sample.name.endswith("_total"):
                handled += sample.value
                if sample.labels.get("status_class") == "5xx":
                    errors += sample.value
    in_flight = sum(sample.value for family in metrics["in_flight"].collect() for sample in family.samples)
    return {"active_requests": int(in_flight), "request_count": int(handled), "error_count": int(errors)}


def exposition() -> tuple[bytes, str]:
    """The registry in the Prometheus text format, with its content type."""
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return generate_latest(_get()["registry"]), CONTENT_TYPE_LATEST


__all__ = ["HttpMetricsMiddleware", "exposition", "request_snapshot", "route_template", "status_class"]
