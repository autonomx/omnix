"""Gateway diagnostics summary for platform contracts."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.gateway.workers import WorkerHealthPayload, get_worker_health_payload


class DiagnosticsPayload(BaseModel):
    ok: bool
    status: str
    workers: WorkerHealthPayload
    event_stream: dict[str, str] = Field(default_factory=dict)
    logs: list[dict[str, str]] = Field(default_factory=list)


def get_diagnostics_payload() -> DiagnosticsPayload:
    workers = get_worker_health_payload()
    return DiagnosticsPayload(
        ok=workers.ok,
        status="ready" if workers.ok else "degraded",
        workers=workers,
        event_stream={
            "transport": "sse",
            "client": "apps/web/src/events/eventClient.ts",
            "status": "available",
        },
        logs=[],
    )
