"""Prometheus metrics for the gateway (WP-10.3).

The registry is built on first use, not at import: ``prometheus_client``
imports 28 modules, and composing the gateway records nothing. The catalog is
documented in ``docs/operations/METRICS.md``. Labels stay bounded: routes are
templates (``/api/chat/sessions/{session_id}``), never raw paths, and statuses
are classes (``2xx`` ... ``5xx``).
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

logger = logging.getLogger(__name__)
_UNMATCHED_ROUTE = "unmatched"
_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)
_LOOP_LAG_BUCKETS = (0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
LOOP_LAG_INTERVAL_SECONDS = 0.5
_lock = threading.Lock()
_metrics: dict[str, Any] | None = None


_METRIC_NAMES = (
    "requests", "latency", "in_flight", "provider_calls", "provider_latency", "provider_retries", "loop_lag",
    "auth_rejections", "rate_limited", "retention_deleted",
)


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
        "provider_calls": Counter(
            "omnix_provider_calls", "Provider and model-service HTTP attempts by client and outcome.",
            ("client", "outcome"), registry=registry,
        ),
        "provider_latency": Histogram(
            "omnix_provider_response_seconds",
            "Time from sending a provider request to its response headers, by client.",
            ("client",), buckets=_LATENCY_BUCKETS, registry=registry,
        ),
        "provider_retries": Counter(
            "omnix_provider_retries", "Provider requests sent again after a retryable failure.",
            ("client",), registry=registry,
        ),
        "auth_rejections": Counter(
            "omnix_auth_rejections", "Requests refused by sign-in, CSRF or permission checks, by reason.",
            ("reason",), registry=registry,
        ),
        "rate_limited": Counter(
            "omnix_rate_limit_rejections", "Requests refused by a rate limit, by limit.", ("limit",), registry=registry,
        ),
        "retention_deleted": Counter(
            "omnix_retention_rows_deleted", "Rows deleted by retention, by record type.", ("record_type",),
            registry=registry,
        ),
        "loop_lag": Histogram(
            "omnix_event_loop_lag_seconds", "How late the event loop woke a sleeping task, sampled twice a second.",
            buckets=_LOOP_LAG_BUCKETS, registry=registry,
        ),
    }


class _Unrecorded:
    """Stands in for every metric where ``prometheus_client`` is not installed.

    The TTS and STT service environments do not lock it; their outbound
    pooled calls must not fail for want of a metrics library.
    """

    def labels(self, *_values: str) -> _Unrecorded:
        return self

    def inc(self, *_args: float) -> None:
        return None

    def dec(self, *_args: float) -> None:
        return None

    def observe(self, *_args: float) -> None:
        return None

    def collect(self) -> list[Any]:
        return []


def _get() -> dict[str, Any]:
    global _metrics
    if _metrics is None:
        with _lock:
            if _metrics is None:
                try:
                    _metrics = _build()
                except ImportError:
                    logger.info("prometheus_client is not installed; metrics are not recorded")
                    _metrics = {"registry": None, **{name: _Unrecorded() for name in _METRIC_NAMES}}
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


def record_provider_attempt(client: str, status: int | str, seconds: float | None = None) -> None:
    """One HTTP attempt by a pooled client: a response status, ``transport_error`` or ``circuit_open``."""
    metrics = _get()
    outcome = status_class(status) if isinstance(status, int) else status
    metrics["provider_calls"].labels(client, outcome).inc()
    if seconds is not None:
        metrics["provider_latency"].labels(client).observe(seconds)


def record_provider_retry(client: str) -> None:
    _get()["provider_retries"].labels(client).inc()


def record_auth_rejection(reason: str) -> None:
    """A refusal by sign-in, CSRF or a permission check; ``reason`` is the response's fixed code."""
    _get()["auth_rejections"].labels(reason).inc()


def record_rate_limit_rejection(limit: str) -> None:
    _get()["rate_limited"].labels(limit).inc()


def record_retention_deleted(record_type: str, rows: int) -> None:
    _get()["retention_deleted"].labels(record_type).inc(rows)


class SchedulerCollector:
    """This process's scheduled tasks, read from the scheduler's diagnostics at scrape time.

    Only the process that owns the background lock runs tasks; elsewhere the
    counters stay at zero.
    """

    def __init__(self, diagnostics: Callable[[], dict[str, Any]]) -> None:
        self.diagnostics = diagnostics

    def collect(self) -> Iterator[Any]:
        from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

        tasks = self.diagnostics().get("tasks") or {}
        runs = CounterMetricFamily("omnix_scheduler_task_runs", "Scheduled task runs.", labels=["task"])
        failures = CounterMetricFamily("omnix_scheduler_task_failures", "Scheduled task runs that failed.", labels=["task"])
        timeouts = CounterMetricFamily(
            "omnix_scheduler_task_timeouts", "Scheduled task runs stopped at their timeout.", labels=["task"],
        )
        duration = GaugeMetricFamily(
            "omnix_scheduler_task_last_duration_seconds", "Duration of the task's last run.", labels=["task"],
        )
        lag = GaugeMetricFamily(
            "omnix_scheduler_task_last_lag_seconds", "How late the task's last run started.", labels=["task"],
        )
        for task, metric in sorted(tasks.items()):
            runs.add_metric([task], metric.get("run_count") or 0)
            failures.add_metric([task], metric.get("failure_count") or 0)
            timeouts.add_metric([task], metric.get("timeout_count") or 0)
            if metric.get("last_duration_seconds") is not None:
                duration.add_metric([task], metric["last_duration_seconds"])
            if metric.get("last_lag_seconds") is not None:
                lag.add_metric([task], metric["last_lag_seconds"])
        yield from (runs, failures, timeouts, duration, lag)


def install_provider_metrics() -> None:
    """Record every pooled provider and model-service call in this process."""
    from app.runtime.http_client import set_attempt_observers

    set_attempt_observers(record_provider_attempt, record_provider_retry)


@contextlib.asynccontextmanager
async def event_loop_lag_monitor(interval: float = LOOP_LAG_INTERVAL_SECONDS) -> AsyncIterator[None]:
    """Sample this event loop's lag while the block runs (the gateway lifespan).

    A task sleeps ``interval`` and records how much later than that it woke:
    time the loop spent in blocking code instead of serving requests.
    """
    histogram = _get()["loop_lag"]

    async def sample() -> None:
        loop = asyncio.get_running_loop()
        while True:
            started = loop.time()
            await asyncio.sleep(interval)
            histogram.observe(max(0.0, loop.time() - started - interval))

    task = asyncio.create_task(sample(), name="omnix-event-loop-lag")
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


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


class DurableStateCollector:
    """Job queue and outbox gauges read at scrape time from ``snapshot`` (a database read).

    The values describe the workspace, not this process: every gateway
    process reports the same numbers, so aggregate them with ``max``.
    """

    def __init__(self, snapshot: Callable[[], dict[str, Any]]) -> None:
        self.snapshot = snapshot

    def collect(self) -> Iterator[Any]:
        from prometheus_client.core import GaugeMetricFamily

        up = GaugeMetricFamily("omnix_jobs_snapshot_up", "1 when the job queue snapshot was read, else 0.")
        try:
            data = self.snapshot()
        except Exception as exc:
            # No exception text: it can carry a database URL.
            logger.warning("job metrics snapshot failed error_type=%s", type(exc).__name__)
            up.add_metric([], 0)
            yield up
            return
        up.add_metric([], 1)
        yield up
        active = GaugeMetricFamily("omnix_jobs_active", "Active jobs by type and status.", labels=["job_type", "status"])
        oldest = GaugeMetricFamily(
            "omnix_jobs_oldest_waiting_age_seconds",
            "Age of the oldest job waiting to be claimed (queued, waiting or retrying), by type.",
            labels=["job_type"],
        )
        expired = GaugeMetricFamily(
            "omnix_jobs_expired_leases", "Active jobs whose lease has expired, by type.", labels=["job_type"],
        )
        oldest_by_type: dict[str, float] = {}
        expired_by_type: dict[str, int] = {}
        for row in data["active"]:
            job_type = row["job_type"]
            active.add_metric([job_type, row["status"]], row["count"])
            oldest_by_type[job_type] = max(oldest_by_type.get(job_type, 0.0), row["oldest_waiting_age_seconds"])
            expired_by_type[job_type] = expired_by_type.get(job_type, 0) + row["expired_leases"]
        for job_type, age in sorted(oldest_by_type.items()):
            oldest.add_metric([job_type], age)
        for job_type, count in sorted(expired_by_type.items()):
            expired.add_metric([job_type], count)
        dead = GaugeMetricFamily("omnix_job_dead_letters", "Unresolved dead-lettered jobs.")
        dead.add_metric([], data["dead_letter_count"])
        yield from (active, oldest, expired, dead)
        outbox = data.get("outbox")
        if outbox is not None:
            for name, key, help_text in _OUTBOX_GAUGES:
                family = GaugeMetricFamily(name, help_text)
                family.add_metric([], outbox[key])
                yield family


_OUTBOX_GAUGES = (
    ("omnix_outbox_unpublished", "unpublished", "Outbox events not yet delivered by the relay."),
    ("omnix_outbox_oldest_unpublished_age_seconds", "oldest_unpublished_age_seconds",
     "Age of the oldest undelivered outbox event."),
    ("omnix_outbox_dead_letters", "dead_letters", "Outbox events the relay gave up on."),
)
# psycopg_pool statistics: cumulative counters (nothing calls pop_stats) and
# current gauges.
_POOL_GAUGES = (
    ("omnix_db_pool_size", "pool_size", "Connections the pool holds."),
    ("omnix_db_pool_in_use", "pool_used", "Connections lent out."),
    ("omnix_db_pool_max", "pool_max", "Connections the pool may hold."),
    ("omnix_db_pool_requests_waiting", "requests_waiting", "Callers waiting for a connection."),
)
_POOL_COUNTERS = (
    ("omnix_db_pool_requests", "requests_num", 1.0, "Connection requests."),
    ("omnix_db_pool_request_wait_seconds", "requests_wait_ms", 0.001, "Time callers spent waiting for a connection."),
    ("omnix_db_pool_request_errors", "requests_errors", 1.0, "Connection requests that timed out or failed."),
    ("omnix_db_pool_connections_lost", "connections_lost", 1.0, "Pooled connections found broken."),
)


class PoolCollector:
    """This process's PostgreSQL pool, read from ``stats`` at scrape time."""

    def __init__(self, stats: Callable[[], dict[str, Any]]) -> None:
        self.stats = stats

    def collect(self) -> Iterator[Any]:
        from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

        stats = self.stats()
        if not stats:
            return
        for name, key, help_text in _POOL_GAUGES:
            family = GaugeMetricFamily(name, help_text)
            family.add_metric([], float(stats.get(key, 0)))
            yield family
        for name, key, scale, help_text in _POOL_COUNTERS:
            counter = CounterMetricFamily(name, help_text)
            counter.add_metric([], float(stats.get(key, 0)) * scale)
            yield counter


def exposition(*collectors: Any) -> tuple[bytes, str]:
    """The registry, then each scrape-time collector, in the Prometheus text format."""
    from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest

    body = generate_latest(_get()["registry"])
    for collector in collectors:
        scrape = CollectorRegistry(auto_describe=False)
        scrape.register(collector)
        body += generate_latest(scrape)
    return body, CONTENT_TYPE_LATEST


__all__ = [
    "DurableStateCollector", "HttpMetricsMiddleware", "PoolCollector", "SchedulerCollector",
    "event_loop_lag_monitor", "exposition", "record_retention_deleted",
    "install_provider_metrics", "record_auth_rejection", "record_provider_attempt", "record_provider_retry",
    "record_rate_limit_rejection", "request_snapshot", "route_template", "status_class",
]
