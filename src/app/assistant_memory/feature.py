"""Assistant-memory feature declaration."""
from __future__ import annotations

from fastapi import APIRouter

from app.assistant_memory.jobs import (
    MEMORY_SUGGEST_JOB_TYPE,
    MemorySuggestionJobInput,
    process_memory_suggestion_job,
)
from app.assistant_memory.owner_defaults import default_memory_service
from app.jobs.handlers import JobExecutionContext, JobHandlerSpec
from app.jobs.models import JobRecord, ResourceClass
from app.runtime.features import FeatureContext, FeatureModule
from app.assistant_memory.persistence.repository_specs import (
    ASSISTANT_MEMORY_REPOSITORY_SPECS,
)
from app.assistant_memory.persistence.settings_store import assistant_memory_setting_spec

from .routes import register_assistant_memory_routes


def _execute_memory_suggestion(
    context: JobExecutionContext,
    job: JobRecord,
) -> JobRecord:
    services = context.services
    chat_store = getattr(services, "chat", None)
    if chat_store is None:
        raise RuntimeError("assistant memory job requires the chat service")
    process_memory_suggestion_job(
        job,
        chat_store=chat_store,
        memory_service=default_memory_service(),
        job_store=context.job_store,
        already_claimed=job.lease is not None,
    )
    return context.job_store.get_job(job.id) or job


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
    job_handlers=(
        JobHandlerSpec(
            type=MEMORY_SUGGEST_JOB_TYPE,
            handler=_execute_memory_suggestion,
            input_model=MemorySuggestionJobInput,
            resource_class=ResourceClass.CPU,
            timeout_seconds=300,
            max_attempts=3,
        ),
    ),
    repositories=ASSISTANT_MEMORY_REPOSITORY_SPECS,
    settings=(assistant_memory_setting_spec(),),
)
