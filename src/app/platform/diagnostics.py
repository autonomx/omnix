"""Gateway diagnostics summary for platform contracts."""
from __future__ import annotations

from pydantic import BaseModel, Field
import re

from app.gateway.workers import WorkerHealthPayload, get_worker_health_payload
from app.jobs import ModelResidencyDiagnostics, ModelResidencyRecord, get_model_residency_diagnostics
from app.providers.cache_status import ProviderModelCachePayload, get_provider_model_cache_status
from .runtime_diagnostics import RuntimeDiagnostics


class DiagnosticsPayload(BaseModel):
    ok: bool
    status: str
    workers: WorkerHealthPayload
    event_stream: dict[str, str] = Field(default_factory=dict)
    model_residency: ModelResidencyDiagnostics = Field(default_factory=get_model_residency_diagnostics)
    provider_model_cache: ProviderModelCachePayload = Field(default_factory=get_provider_model_cache_status)
    logs: list[dict[str, str]] = Field(default_factory=list)
    runtime: RuntimeDiagnostics | None = None


def get_diagnostics_payload(model_residency_records: list[ModelResidencyRecord] | None = None) -> DiagnosticsPayload:
    workers = get_worker_health_payload()
    return DiagnosticsPayload(
        ok=workers.ok,
        status="ready" if workers.ok else "degraded",
        workers=workers,
        event_stream={
            "transport": "sse",
            "client": "src/apps/web/src/events/eventClient.ts",
            "status": "available",
        },
        model_residency=get_model_residency_diagnostics(model_residency_records),
        provider_model_cache=get_provider_model_cache_status(),
        logs=[],
    )


def redact_diagnostics(value, key=''):
    """Redact nested service metadata as well as credentials embedded in URLs."""
    if any(part in key.lower() for part in ('password', 'api_key', 'secret', 'credential', 'token')):
        return '[REDACTED]' if value not in (None, '') else value
    if isinstance(value, dict):
        return {str(name): redact_diagnostics(item, str(name)) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_diagnostics(item) for item in value]
    if isinstance(value, str):
        return re.sub(r'([a-z][a-z0-9+.-]*://)[^\s/@]+@', r'\1[REDACTED]@', value, flags=re.I)
    return value


def get_runtime_diagnostics_payload(gateway, *, model_residency_store_factory) -> DiagnosticsPayload:
    """Keep local ownership diagnostics available when durable reads fail."""
    from app.jobs.residency import GpuResidencyPolicy
    from .runtime_diagnostics import runtime_diagnostics

    runtime = runtime_diagnostics(gateway)
    error_class = runtime.postgresql.get('error_class')
    payload = None
    if runtime.postgresql.get('connectivity') is not False:
        try:
            payload = get_diagnostics_payload(model_residency_store_factory().list_records())
        except Exception as exc:
            error_class = type(exc).__name__
    if payload is None:
        payload = DiagnosticsPayload(
            ok=False, status='degraded', workers=get_worker_health_payload(),
            model_residency=ModelResidencyDiagnostics(status='unavailable', policy=GpuResidencyPolicy()),
            provider_model_cache=ProviderModelCachePayload(
                status='unavailable', diagnostics=[{'code': 'durable_diagnostics_unavailable', 'error_class': error_class or 'Unavailable'}],
            ),
        )
    payload.runtime = runtime
    tts_worker = next((worker for worker in payload.workers.workers if worker.id == 'tts'), None)
    runtime.tts['endpoint_health'] = {'ok': tts_worker.ok, 'status': tts_worker.status} if tts_worker is not None else None
    return DiagnosticsPayload.model_validate(redact_diagnostics(payload.model_dump()))
