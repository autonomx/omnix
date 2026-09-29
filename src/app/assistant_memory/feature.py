"""Assistant-memory feature declaration."""
from __future__ import annotations

from fastapi import APIRouter

from app.runtime.features import FeatureContext, FeatureModule
from app.assistant_memory.persistence.repository_specs import (
    ASSISTANT_MEMORY_REPOSITORY_SPECS,
)
from app.assistant_memory.persistence.settings_store import assistant_memory_setting_spec

from .routes import register_assistant_memory_routes


def _router(context: FeatureContext) -> APIRouter:
    router = APIRouter()
    services = context.services
    kwargs = {"chat_store_factory": lambda: services.chat}
    settings_service = getattr(services, "settings", None)
    if settings_service is not None:
        from app.assistant_memory.persistence.settings_store import (
            SettingsServiceAssistantMemorySettingsStore,
        )

        kwargs["memory_settings_store_factory"] = lambda: (
            SettingsServiceAssistantMemorySettingsStore(settings_service)
        )
    register_assistant_memory_routes(router, **kwargs)
    return router

FEATURE = FeatureModule(
    id="assistant-memory",
    title="Assistant Memory",
    depends_on=("chat",),
    routers=(_router,),
    repositories=ASSISTANT_MEMORY_REPOSITORY_SPECS,
    settings=(assistant_memory_setting_spec(),),
)
