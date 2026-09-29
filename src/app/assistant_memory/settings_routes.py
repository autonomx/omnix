"""Internal Chat memory settings and content-free diagnostics routes."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, HTTPException

from .observability import CompanionMemoryMetrics, companion_metrics_snapshot
from .settings import (
    AssistantMemoryRuntimeStatus,
    AssistantMemorySettingsStore,
    default_memory_settings_store,
    AssistantMemorySettingsUpdate,
)
from .persistence.settings_store import SettingRevisionConflict


def register_memory_settings_routes(
    app: FastAPI,
    *,
    settings_store_factory: Callable[[], AssistantMemorySettingsStore] | None = None,
) -> None:
    settings_store_factory = settings_store_factory or default_memory_settings_store
    names = {getattr(route, "name", "") for route in app.routes}
    if "assistant_memory_settings_status_endpoint" in names:
        return

    @app.get(
        "/api/assistant/memory/settings",
        response_model=AssistantMemoryRuntimeStatus,
        name="assistant_memory_settings_status_endpoint",
    )
    async def assistant_memory_settings_status_endpoint() -> AssistantMemoryRuntimeStatus:
        return settings_store_factory().load_effective()

    @app.post(
        "/api/assistant/memory/settings",
        response_model=AssistantMemoryRuntimeStatus,
        name="assistant_memory_settings_update_endpoint",
    )
    async def assistant_memory_settings_update_endpoint(
        request: AssistantMemorySettingsUpdate,
    ) -> AssistantMemoryRuntimeStatus:
        try:
            return settings_store_factory().update(request)
        except SettingRevisionConflict as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "settings_revision_conflict", "message": str(exc)},
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=403,
                detail={"code": "memory_privacy_policy_rejected", "message": str(exc)},
            ) from exc

    @app.get(
        "/api/assistant/memory/metrics",
        response_model=CompanionMemoryMetrics,
        name="assistant_memory_metrics_endpoint",
    )
    async def assistant_memory_metrics_endpoint() -> CompanionMemoryMetrics:
        return companion_metrics_snapshot()
