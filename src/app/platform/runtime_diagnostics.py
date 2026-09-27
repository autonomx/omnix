"""Read-only, workspace-scoped runtime diagnostics over existing runtime ledgers."""

from __future__ import annotations

import os
import threading
import time
from typing import Any

from pydantic import BaseModel, Field


class RuntimeDiagnostics(BaseModel):
    schema_version: int = 1
    process: dict[str, Any] = Field(default_factory=dict)
    postgresql: dict[str, Any] = Field(default_factory=dict)
    background: dict[str, Any] = Field(default_factory=dict)
    jobs: dict[str, Any] = Field(default_factory=dict)
    chat: dict[str, Any] = Field(default_factory=dict)
    tts: dict[str, Any] = Field(default_factory=dict)
    replicas: dict[str, Any] = Field(default_factory=dict)


class RequestMetrics:
    def __init__(self):
        self.started_at = time.monotonic()
        self._lock = threading.Lock()
        self.active_requests = self.request_count = self.error_count = 0

    def snapshot(self):
        with self._lock:
            return {"active_requests": self.active_requests, "request_count": self.request_count, "error_count": self.error_count}


class RuntimeRequestMiddleware:
    def __init__(self, app, metrics):
        self.app, self.metrics = app, metrics

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        with self.metrics._lock:
            self.metrics.active_requests += 1
            self.metrics.request_count += 1
        failed = False

        async def tracked_send(message):
            nonlocal failed
            if message['type'] == 'http.response.start' and message['status'] >= 500:
                failed = True
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        except Exception:
            failed = True
            raise
        finally:
            with self.metrics._lock:
                self.metrics.active_requests -= 1
                self.metrics.error_count += int(failed)


def _durable_snapshot(services):
    from app.persistence.authority import AuthorityOperation, require_authority_operation

    jobs = services.jobs
    database, workspace = jobs.database, jobs.context.workspace_id
    with database.connection() as connection:
        policy = require_authority_operation(connection, AuthorityOperation.DIAGNOSTIC_READ)
        groups = connection.execute(
            "SELECT resource_class, status, count(*), "
            "COALESCE(max(EXTRACT(EPOCH FROM (clock_timestamp() - created_at))) FILTER (WHERE status = 'queued'), 0), "
            "count(*) FILTER (WHERE lease_expires_at < clock_timestamp()) "
            "FROM omnix_jobs WHERE workspace_id = %s GROUP BY resource_class, status",
            (workspace,),
        ).fetchall()
        dead_letters = connection.execute(
            "SELECT count(*) FROM omnix_dead_letters WHERE workspace_id = %s AND resolved_at IS NULL", (workspace,),
        ).fetchone()[0]
        events = connection.execute(
            "SELECT event_type, count(*) FROM omnix_job_events WHERE workspace_id = %s "
            "AND created_at > clock_timestamp() - INTERVAL '60 seconds' GROUP BY event_type", (workspace,),
        ).fetchall()
        session_owners = connection.execute(
            "SELECT count(DISTINCT input_payload ->> 'session_id') FROM omnix_jobs "
            "WHERE workspace_id = %s AND job_type = 'chat.generate' AND status = 'running'", (workspace,),
        ).fetchone()[0]
    return {
        "connectivity": True, "authority_state": policy.authority_state,
        "statement_timeout_ms": database.settings.statement_timeout_ms,
        "pool": database.pool_statistics(),
    }, {
        "available": True,
        "by_resource_class": [{"resource_class": resource, "status": status, "count": count} for resource, status, count, _, _ in groups],
        "oldest_queued_age_seconds": max((float(row[3]) for row in groups), default=0),
        "expired_lease_count": sum(row[4] for row in groups),
        "dead_letter_count": dead_letters,
        "events_last_60_seconds": dict(events),
        "claim_rate_per_second": dict(events).get('job.claimed', 0) / 60,
        "failure_rate_per_second": dict(events).get('job.failed', 0) / 60,
        "retry_rate_per_second": dict(events).get('job.retry_scheduled', 0) / 60,
    }, session_owners


def runtime_diagnostics(gateway) -> RuntimeDiagnostics:
    config, capabilities = gateway.state.runtime_config, gateway.state.runtime_capabilities
    metrics = gateway.state.runtime_metrics
    owner = getattr(gateway.state, 'execution_owner', None)
    background = getattr(gateway.state, 'background_runtime', None)
    services = getattr(gateway.state, 'runtime_services', None)
    postgres, jobs, sessions = {"connectivity": None}, {"available": False}, None
    if services is not None:
        try:
            postgres, jobs, sessions = _durable_snapshot(services)
            postgres['migrations_pending'] = gateway.state.persistence_startup.get('migrations_pending', [])
        except Exception as exc:
            # No exception message or database URL crosses this boundary.
            postgres = {"connectivity": False, "error_class": type(exc).__name__}
    dispatcher = getattr(getattr(services, 'jobs', None), 'chat_dispatcher', None)
    chat = dispatcher.diagnostics() if dispatcher is not None else {}
    chat['active_session_ownership'] = sessions
    if owner is not None:
        chat.update(owner.recovery_diagnostics())
        chat['execution_owner_healthy'] = owner.healthy
    from app.gateway.tts_stream_diagnostics import runtime_stream_snapshot
    resolver = getattr(gateway.state, 'live_voice_tts_provider_resolver', None)
    delivery = getattr(gateway.state, 'live_voice_delivery_persistence_worker', None)
    return RuntimeDiagnostics(
        process={"process_id": os.getpid(), "runtime_id": getattr(owner, 'node_id', None),
                 "gateway_role": config.gateway_role.value, "uptime_seconds": time.monotonic() - metrics.started_at,
                 "build_revision": config.build_revision, "capabilities": sorted(value.value for value in capabilities.granted),
                 **metrics.snapshot()},
        postgresql=postgres,
        background=background.diagnostics() if background is not None else {"role": config.gateway_role.value, "owns_lock": False},
        jobs=jobs, chat=chat,
        tts={"mode": 'remote' if config.use_remote_tts else 'local' if config.allow_local_tts else 'worker_routed',
             "endpoint": config.tts.url if config.tts else None, **runtime_stream_snapshot(),
             "provider_refresh": resolver.diagnostics() if resolver is not None else {},
             "delivery_queue": delivery.diagnostics() if delivery is not None else {}},
        replicas={"known_origins": list(config.api_replica_origins), "local_runtime_started": gateway.state.runtime_started,
                  "remote_readiness": None},
    )
