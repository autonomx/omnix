"""Browser-facing assistant context routes."""
from __future__ import annotations

import asyncio
from collections.abc import Callable

from fastapi import FastAPI, HTTPException

from app.chat import ChatSessionStore, SendChatMessageRequest, SendChatMessageResponse, default_chat_store
from app.chat.research_citations import validate_completed_research_reply
from app.chat.research_jobs import link_user_message_to_research_job
from app.jobs import CreateJobRequest, JobStatus, ResourceClass, SQLiteJobStore, default_job_store
from app.research.contracts import RESEARCH_JOB_TYPE
from app.research.jobs import DeepResearchJobInput, create_deep_research_job_request
from app.research.policy import ResearchPolicy, ResearchRateLimitError, ResearchRateLimiter
from app.research.settings import ResearchRuntimeSettings, load_research_runtime_settings
from app.research.status import ResearchRuntimeStatus, research_runtime_status

from .models import AssistantContextChatRequest
from .service import AssistantContextService, default_assistant_context_service

_ROUTE_NAME = "assistant_context_chat_message_endpoint"
_STATUS_ROUTE_NAME = "assistant_research_runtime_status_endpoint"
_ACTIVE_RESEARCH_STATUSES = {
    JobStatus.QUEUED,
    JobStatus.LEASED,
    JobStatus.RUNNING,
    JobStatus.WAITING,
    JobStatus.RETRYING,
    JobStatus.CANCEL_REQUESTED,
}


def register_assistant_context_routes(
    app: FastAPI,
    *,
    chat_store_factory: Callable[[], ChatSessionStore] = default_chat_store,
    job_store_factory: Callable[[], SQLiteJobStore] = default_job_store,
    context_service_factory: Callable[[], AssistantContextService] = default_assistant_context_service,
    rate_limiter_factory: Callable[[], ResearchRateLimiter] = ResearchRateLimiter,
    policy_factory: Callable[[], ResearchPolicy] | None = None,
    settings_factory: Callable[[], ResearchRuntimeSettings] = load_research_runtime_settings,
) -> None:
    route_names = {getattr(route, "name", "") for route in app.routes}
    if _STATUS_ROUTE_NAME not in route_names:

        @app.get(
            "/api/assistant/research/status",
            response_model=ResearchRuntimeStatus,
            name=_STATUS_ROUTE_NAME,
        )
        async def assistant_research_runtime_status_endpoint() -> ResearchRuntimeStatus:
            return research_runtime_status(settings_factory())

    if _ROUTE_NAME in route_names:
        return

    @app.post(
        "/api/assistant/context/chat/sessions/{session_id}/messages",
        response_model=SendChatMessageResponse,
        include_in_schema=False,
        name=_ROUTE_NAME,
    )
    async def assistant_context_chat_message_endpoint(
        session_id: str,
        request: AssistantContextChatRequest,
    ) -> SendChatMessageResponse:
        settings = settings_factory()
        policy = policy_factory() if policy_factory is not None else settings.policy
        request.internal_research_identity = session_id
        request.internal_research_provider = settings.provider
        request.internal_research_policy = {
            "search_cache_ttl_seconds": policy.search_cache_ttl_seconds,
            "extraction_cache_ttl_seconds": policy.extraction_cache_ttl_seconds,
            "quick_requests_per_minute": policy.quick_requests_per_minute,
            "deep_requests_per_hour": policy.deep_requests_per_hour,
            "provider_requests_per_minute": policy.provider_requests_per_minute,
            "raw_snapshot_retention_days": policy.raw_snapshot_retention_days,
            "source_manifest_retention_days": policy.source_manifest_retention_days,
            "max_active_deep_jobs_per_session": policy.max_active_deep_jobs_per_session,
            "planner_receives_conversation_history": False,
            "synthesis_receives_raw_page_bodies": False,
        }
        request.web_search_max_results = settings.max_results
        limiter = rate_limiter_factory()
        try:
            if request.web_research_mode == "quick":
                limiter.quick_request(session_id, policy)
            elif request.web_research_mode == "deep":
                limiter.deep_request(session_id, policy)
        except ResearchRateLimitError as exc:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "research_rate_limited",
                    "action": exc.action,
                    "retry_after_seconds": exc.retry_after_seconds,
                },
            ) from exc

        if request.web_research_mode == "deep":
            return _begin_deep_research(
                session_id,
                request,
                chat_store=chat_store_factory(),
                job_store=job_store_factory(),
                policy=policy,
                settings=settings,
            )

        context = await asyncio.to_thread(context_service_factory().build, request)
        context_items = [item.model_dump(mode="json") for item in context.items]
        send_request = _send_request(request)
        chat_store = chat_store_factory()
        appended = chat_store.append_user_message(
            session_id,
            send_request,
            context_items=context_items,
            context_diagnostics=context.diagnostics,
        )
        if appended is None:
            raise HTTPException(status_code=404, detail="chat session not found")
        session, user_message = appended
        validated = validate_completed_research_reply(
            chat_store,
            session.id,
            user_message.id,
            context_items,
            show_diagnostics=settings.show_diagnostics,
        )
        if validated is not None:
            session = validated
        job = job_store_factory().create_job(
            CreateJobRequest(
                module="chatbot",
                type="chat.generate",
                resource_class=ResourceClass.GPU_LLM,
                input_payload={
                    "session_id": session.id,
                    "message_id": user_message.id,
                    "provider_id": request.provider_id or session.provider_id,
                    "model_id": request.model_id or session.model_id,
                    "context_sources": [item.source_id for item in context.items],
                    "context_diagnostics": context.diagnostics,
                },
                compat={"contract": "assistant_context_chat_v1"},
            )
        )
        return SendChatMessageResponse(session=session, user_message=user_message, job=job)


def _begin_deep_research(
    session_id: str,
    request: AssistantContextChatRequest,
    *,
    chat_store: ChatSessionStore,
    job_store: SQLiteJobStore,
    policy: ResearchPolicy,
    settings: ResearchRuntimeSettings,
) -> SendChatMessageResponse:
    active_jobs = [
        job
        for job in job_store.list_jobs()
        if job.type == RESEARCH_JOB_TYPE
        and job.owner_id == session_id
        and job.status in _ACTIVE_RESEARCH_STATUSES
    ]
    if len(active_jobs) >= policy.max_active_deep_jobs_per_session:
        raise HTTPException(status_code=409, detail="deep_research_already_active")

    appended = chat_store.begin_user_message(
        session_id,
        _send_request(request),
        context_diagnostics={
            "web_research_mode": "deep",
            "web_search_status": "queued_as_durable_research_job",
            "research_provider": settings.provider,
        },
    )
    if appended is None:
        raise HTTPException(status_code=404, detail="chat session not found")
    session, user_message = appended
    job = job_store.create_job(
        create_deep_research_job_request(
            DeepResearchJobInput(
                session_id=session.id,
                user_message_id=user_message.id,
                question=request.content,
                provider_id=request.provider_id or session.provider_id,
                model_id=request.model_id or session.model_id,
                research_provider=settings.provider,
                max_steps=settings.max_steps,
                max_queries=settings.max_queries,
                max_sources=settings.max_sources,
                max_extracts=settings.max_extracts,
                search_cache_ttl_seconds=policy.search_cache_ttl_seconds,
                extraction_cache_ttl_seconds=policy.extraction_cache_ttl_seconds,
                hermes_planner_enabled=settings.hermes_planner_enabled,
                metadata={
                    "agent_mode": request.agent_mode,
                    "dry_run": request.dry_run,
                    "diagnostics_enabled": settings.show_diagnostics,
                },
            )
        )
    )
    linked = link_user_message_to_research_job(
        chat_store,
        session.id,
        user_message.id,
        job.id,
    )
    if linked is not None:
        session, user_message = linked
    return SendChatMessageResponse(session=session, user_message=user_message, job=job)


def _send_request(request: AssistantContextChatRequest) -> SendChatMessageRequest:
    return SendChatMessageRequest(
        content=request.content,
        provider_id=request.provider_id,
        model_id=request.model_id,
        agent_mode=request.agent_mode,
        dry_run=request.dry_run,
        research_mode=request.web_research_mode,
    )
