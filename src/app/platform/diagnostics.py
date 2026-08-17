"""Gateway diagnostics summary for platform contracts."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.gateway.workers import WorkerHealthPayload, get_worker_health_payload
from app.jobs import ModelResidencyDiagnostics, ModelResidencyRecord, get_model_residency_diagnostics
from app.providers.cache_status import ProviderModelCachePayload, get_provider_model_cache_status


class DiagnosticsPayload(BaseModel):
    ok: bool
    status: str
    workers: WorkerHealthPayload
    event_stream: dict[str, str] = Field(default_factory=dict)
    model_residency: ModelResidencyDiagnostics = Field(default_factory=get_model_residency_diagnostics)
    provider_model_cache: ProviderModelCachePayload = Field(default_factory=get_provider_model_cache_status)
    logs: list[dict[str, str]] = Field(default_factory=list)


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
