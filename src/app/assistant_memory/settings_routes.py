"""Internal Chat memory settings and content-free diagnostics routes."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, HTTPException

from .observability import CompanionMemoryMetrics, companion_metrics_snapshot
from .settings import (
    AssistantMemoryRuntimeStatus,
    AssistantMemorySettingsStore,
    AssistantMemorySettingsUpdate,
)


def register_memory_settings_routes(
    app: FastAPI,
    *,
    settings_store_factory: Callable[[], AssistantMemorySettingsStore] = AssistantMemorySettingsStore,
) -> None:
    names = {getattr(route, "name", "") for route in app.routes}
    if "assistant_memory_settings_status_endpoint" in names:
        return

    @app.get(
        "/api/assistant/memory/settings",
        response_model=AssistantMemoryRuntimeStatus,
        include_in_schema=False,
        name="assistant_memory_settings_status_endpoint",
    )
    async def assistant_memory_settings_status_endpoint() -> AssistantMemoryRuntimeStatus:
        return settings_store_factory().load_effective()

    @app.post(
        "/api/assistant/memory/settings",
        response_model=AssistantMemoryRuntimeStatus,
        include_in_schema=False,
        name="assistant_memory_settings_update_endpoint",
    )
    async def assistant_memory_settings_update_endpoint(
        request: AssistantMemorySettingsUpdate,
    ) -> AssistantMemoryRuntimeStatus:
        try:
            return settings_store_factory().update(request)
        except ValueError as exc:
            raise HTTPException(
                status_code=403,
                detail={"code": "memory_privacy_policy_rejected", "message": str(exc)},
            ) from exc

    @app.get(
        "/api/assistant/memory/metrics",
        response_model=CompanionMemoryMetrics,
        include_in_schema=False,
        name="assistant_memory_metrics_endpoint",
    )
    async def assistant_memory_metrics_endpoint() -> CompanionMemoryMetrics:
        return companion_metrics_snapshot()
