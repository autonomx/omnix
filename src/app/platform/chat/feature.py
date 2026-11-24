"""Chat feature declaration."""
from fastapi import APIRouter

from app.jobs.handlers import JobExecutionContext, JobHandlerSpec
from app.jobs.models import ResourceClass
from app.runtime.features import FeatureModule
from app.platform.chat.persistence.repository_specs import CHAT_REPOSITORY_SPECS


def _chat_context_router(context):
    from app.persistence.runtime import uses_postgresql_runtime
    from app.platform.chat.assistant_context.routes import register_assistant_context_routes
    from .live_call_prewarm import register_live_call_prewarm_routes
    from .live_call_task_routes import register_live_call_task_routes
    from .live_chat_evaluation_routes import create_live_chat_evaluation_router
    from .live_chat_speculation import register_live_chat_speculation_routes
    from .live_chat_speculation_handshake import register_live_chat_speculation_handshake_routes
    from .live_chat_speculation_inline_stream import register_live_chat_speculation_inline_stream_routes
    from .live_material_context import create_live_material_context_router
    from .scene_routes import register_scene_routes
    from .live_observation_generation import create_live_observation_generation_router

    if uses_postgresql_runtime():
        from app.platform.chat.persistence.legacy_sessions import install_postgresql_legacy_session_callbacks
        install_postgresql_legacy_session_callbacks()

    router = APIRouter()
    router.include_router(create_live_material_context_router())
    router.include_router(create_live_observation_generation_router())
    services = context.services
    register_assistant_context_routes(
        router,
        chat_store_factory=lambda: services.chat,
        job_store_factory=lambda: services.jobs,
    )
    chat_store_factory = lambda: services.chat
    register_live_chat_speculation_routes(router, chat_store_factory=chat_store_factory)
    register_live_chat_speculation_handshake_routes(router, chat_store_factory=chat_store_factory)
    register_live_chat_speculation_inline_stream_routes(router, chat_store_factory=chat_store_factory)
    register_live_call_prewarm_routes(router, chat_store_factory=chat_store_factory)
    register_live_call_task_routes(router, chat_store_factory=chat_store_factory,
                                   job_store_factory=lambda: services.jobs)
    register_scene_routes(router, chat_store_factory=chat_store_factory)
    router.include_router(create_live_chat_evaluation_router())
    return router


def _research_mode_router(context):
    from .research_mode_routes import create_research_mode_router

    return create_research_mode_router(chat_store_factory=lambda: context.services.chat)


def _rich_replies_router(context):
    from .rich_replies_routes import create_rich_replies_router

    return create_rich_replies_router(chat_store_factory=lambda: context.services.chat)


def _execute_call_action(context: JobExecutionContext, job):
    from .live_call_actions import execute_call_action_job

    return execute_call_action_job(context, job)


def _call_action_handler() -> JobHandlerSpec:
    from .live_call_actions import JOB_TYPE, LiveCallActionInput

    # One attempt: an action a call asked for is told now or not at all, and a write is only ever proposed.
    return JobHandlerSpec(type=JOB_TYPE, handler=_execute_call_action, input_model=LiveCallActionInput,
                          resource_class=ResourceClass.NETWORK, timeout_seconds=120, max_attempts=1)


def _execute_call_recap(context: JobExecutionContext, job):
    from .live_call_recap import execute_call_recap_job

    return execute_call_recap_job(context, job)


def _call_recap_handler() -> JobHandlerSpec:
    from .live_call_recap import JOB_TYPE, LiveCallRecapInput

    # One attempt: a recap is written after the call or not at all; it is never worth a second model call later.
    return JobHandlerSpec(type=JOB_TYPE, handler=_execute_call_recap, input_model=LiveCallRecapInput,
                          resource_class=ResourceClass.NETWORK, timeout_seconds=120, max_attempts=1)


FEATURE = FeatureModule(
    id="chat",
    title="Chat and Realtime",
    tier="platform",
    routers=(_chat_context_router, _research_mode_router, _rich_replies_router),
    repositories=CHAT_REPOSITORY_SPECS,
    job_handlers=(_call_action_handler(), _call_recap_handler()),
)
