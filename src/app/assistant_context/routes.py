"""Browser-facing assistant context routes."""
from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from app.chat import ChatSessionStore, SendChatMessageRequest, SendChatMessageResponse, default_chat_store
from app.chat.research_citations import validate_completed_research_reply
from app.chat.research_jobs import link_user_message_to_research_job
from app.chat.research_release import apply_research_release_decision
from app.jobs import CreateJobRequest, InMemoryJobStore, ResourceClass, default_job_store
from app.research.contracts import RESEARCH_JOB_TYPE
from app.research.jobs import DeepResearchJobInput, create_deep_research_job_request
from app.research.policy import ResearchPolicy
from app.research.release_policy import (
    ResearchReleaseDecision,
    ResearchReleasePolicy,
    research_release_availability,
    research_release_policy_from_env,
    resolve_research_release,
)
from app.research.settings import ResearchRuntimeSettings, load_research_runtime_settings
from app.research.status import ResearchRuntimeStatus, research_runtime_status

from .models import AssistantContextChatRequest
from .service import AssistantContextService, default_assistant_context_service

_ROUTE_NAME = "assistant_context_chat_message_endpoint"
_STREAM_ROUTE_NAME = "assistant_context_stream_chat_message_endpoint"
_STATUS_ROUTE_NAME = "assistant_research_runtime_status_endpoint"


def register_assistant_context_routes(
    app: FastAPI,
    *,
    chat_store_factory: Callable[[], ChatSessionStore] = default_chat_store,
    job_store_factory: Callable[[], InMemoryJobStore] = default_job_store,
    context_service_factory: Callable[[], AssistantContextService] = default_assistant_context_service,
    policy_factory: Callable[[], ResearchPolicy] | None = None,
    settings_factory: Callable[[], ResearchRuntimeSettings] = load_research_runtime_settings,
    release_policy_factory: Callable[[], ResearchReleasePolicy] = research_release_policy_from_env,
) -> None:
    route_names = {getattr(route, "name", "") for route in app.routes}
    if _STATUS_ROUTE_NAME not in route_names:

        @app.get(
            "/api/assistant/research/status",
            response_model=ResearchRuntimeStatus,
            name=_STATUS_ROUTE_NAME,
        )
        async def assistant_research_runtime_status_endpoint(
            session_id: str = "status-preview",
        ) -> ResearchRuntimeStatus:
            return research_runtime_status(
                settings_factory(),
                release_policy_factory(),
                identity=session_id,
            )

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
        release_policy = release_policy_factory()
        decision = resolve_research_release(
            request.web_research_mode,
            settings,
            release_policy,
            identity=session_id,
            allow_downgrade=request.allow_research_downgrade,
        )
        if decision.status == "unavailable":
            availability = research_release_availability(
                settings,
                release_policy,
                identity=session_id,
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "research_mode_unavailable",
                    "requested_mode": decision.requested_mode,
                    "reason": decision.reason,
                    "available_modes": [
                        mode
                        for mode, available in (
                            ("disabled", availability.disabled),
                            ("quick", availability.quick),
                            ("deep", availability.deep),
                        )
                        if available
                    ],
                    "downgrade_available": (
                        decision.requested_mode == "deep" and availability.quick
                    ),
                },
            )

        request.web_research_mode = decision.effective_mode
        request.internal_research_warnings = [
            *request.internal_research_warnings,
            *decision.warnings,
        ]
        policy = policy_factory() if policy_factory is not None else settings.policy
        request.internal_research_identity = session_id
        request.internal_research_provider = settings.effective_provider
        request.internal_research_provider_chain = list(settings.effective_provider_chain)
        request.internal_research_policy = {
            "search_cache_ttl_seconds": policy.search_cache_ttl_seconds,
            "extraction_cache_ttl_seconds": policy.extraction_cache_ttl_seconds,
            "raw_snapshot_retention_days": policy.raw_snapshot_retention_days,
            "source_manifest_retention_days": policy.source_manifest_retention_days,
            "planner_receives_conversation_history": False,
            "synthesis_receives_raw_page_bodies": False,
        }
        request.web_search_max_results = settings.max_results
        if request.web_research_mode == "deep":
            return _begin_deep_research(
                session_id,
                request,
                chat_store=chat_store_factory(),
                job_store=job_store_factory(),
                policy=policy,
                settings=settings,
                decision=decision,
            )

        context = await asyncio.to_thread(context_service_factory().build, request)
        context_items = [item.model_dump(mode="json") for item in context.items]
        send_request = _send_request(request)
        chat_store = chat_store_factory()
        appended = chat_store.append_user_message(
            session_id,
            send_request,
            context_items=context_items,
            context_diagnostics={
                **context.diagnostics,
                "research_requested_mode": decision.requested_mode,
                "research_effective_mode": decision.effective_mode,
                "research_release_status": decision.status,
                "research_release_reason": decision.reason,
                "research_release_warnings": decision.warnings,
            },
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
        released = apply_research_release_decision(
            chat_store,
            session.id,
            user_message.id,
            decision,
        )
        if released is not None:
            session = released
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
                    "research_release": decision.model_dump(mode="json"),
                    "research_compatibility_warnings": request.internal_research_warnings,
                },
                compat={"contract": "assistant_context_chat_v1"},
            )
        )
        return SendChatMessageResponse(session=session, user_message=user_message, job=job)

    @app.post(
        "/api/assistant/context/chat/sessions/{session_id}/messages/stream",
        include_in_schema=False,
        name=_STREAM_ROUTE_NAME,
    )
    async def assistant_context_stream_chat_message_endpoint(
        session_id: str,
        request: AssistantContextChatRequest,
    ) -> StreamingResponse:
        settings = settings_factory()
        release_policy = release_policy_factory()
        decision = resolve_research_release(
            request.web_research_mode,
            settings,
            release_policy,
            identity=session_id,
            allow_downgrade=request.allow_research_downgrade,
        )
        if decision.status == "unavailable":
            availability = research_release_availability(
                settings,
                release_policy,
                identity=session_id,
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "research_mode_unavailable",
                    "requested_mode": decision.requested_mode,
                    "reason": decision.reason,
                    "available_modes": [
                        mode
                        for mode, available in (
                            ("disabled", availability.disabled),
                            ("quick", availability.quick),
                            ("deep", availability.deep),
                        )
                        if available
                    ],
                    "downgrade_available": (
                        decision.requested_mode == "deep" and availability.quick
                    ),
                },
            )

        request.web_research_mode = decision.effective_mode
        request.internal_research_warnings = [
            *request.internal_research_warnings,
            *decision.warnings,
        ]
        policy = policy_factory() if policy_factory is not None else settings.policy
        request.internal_research_identity = session_id
        request.internal_research_provider = settings.effective_provider
        request.internal_research_provider_chain = list(settings.effective_provider_chain)
        request.internal_research_policy = {
            "search_cache_ttl_seconds": policy.search_cache_ttl_seconds,
            "extraction_cache_ttl_seconds": policy.extraction_cache_ttl_seconds,
            "raw_snapshot_retention_days": policy.raw_snapshot_retention_days,
            "source_manifest_retention_days": policy.source_manifest_retention_days,
            "planner_receives_conversation_history": False,
            "synthesis_receives_raw_page_bodies": False,
        }
        request.web_search_max_results = settings.max_results
        chat_store = chat_store_factory()
        if request.web_research_mode == "deep":
            response = _begin_deep_research(
                session_id,
                request,
                chat_store=chat_store,
                job_store=job_store_factory(),
                policy=policy,
                settings=settings,
                decision=decision,
            )

            def generate_deep_research_ack():
                yield _sse({"type": "user_message", "message": response.user_message.model_dump(mode="json")})
                yield _sse({"type": "session", "session": response.session.model_dump(mode="json")})
                yield _sse({"type": "done"})

            return StreamingResponse(generate_deep_research_ack(), media_type="text/event-stream")

        context = await asyncio.to_thread(context_service_factory().build, request)
        context_items = [item.model_dump(mode="json") for item in context.items]
        context_diagnostics = {
            **context.diagnostics,
            "research_requested_mode": decision.requested_mode,
            "research_effective_mode": decision.effective_mode,
            "research_release_status": decision.status,
            "research_release_reason": decision.reason,
            "research_release_warnings": decision.warnings,
        }
        appended = chat_store.begin_user_message(
            session_id,
            _send_request(request),
            context_items=context_items,
            context_diagnostics=context_diagnostics,
        )
        if appended is None:
            raise HTTPException(status_code=404, detail="chat session not found")
        session, user_message = appended

        def generate():
            yield _sse({"type": "user_message", "message": user_message.model_dump(mode="json")})
            content = ""
            metadata: dict[str, Any] = {"generation_status": "completed"}
            try:
                for event in chat_store.stream_provider_reply_chunks(
                    session,
                    user_message,
                    provider_id=request.provider_id or session.provider_id,
                    model_id=request.model_id or session.model_id,
                    context_items=context_items,
                ):
                    if event.get("type") == "complete":
                        content = str(event.get("content") or "").strip()
                        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else metadata
                        if context_items:
                            metadata["context_sources"] = [
                                item.source_id for item in context.items
                            ]
                        metadata["context_diagnostics"] = context_diagnostics
                    yield _sse(event)
                completed = chat_store.complete_streamed_reply(
                    session.id,
                    user_message.id,
                    content,
                    metadata,
                )
                if completed is not None:
                    yield _sse({"type": "session", "session": completed.model_dump(mode="json")})
                yield _sse({"type": "done"})
            except Exception as exc:
                yield _sse({"type": "error", "message": str(exc) or "Chat stream failed."})

        return StreamingResponse(generate(), media_type="text/event-stream")


def _begin_deep_research(
    session_id: str,
    request: AssistantContextChatRequest,
    *,
    chat_store: ChatSessionStore,
    job_store: InMemoryJobStore,
    policy: ResearchPolicy,
    settings: ResearchRuntimeSettings,
    decision: ResearchReleaseDecision,
) -> SendChatMessageResponse:
    research_provider = settings.effective_provider
    research_provider_chain = list(settings.effective_provider_chain)
    appended = chat_store.begin_user_message(
        session_id,
        _send_request(request),
        context_diagnostics={
            "web_research_mode": "deep",
            "web_search_status": "queued_as_durable_research_job",
            "research_provider": research_provider,
            "research_provider_chain": research_provider_chain,
            "research_requested_mode": decision.requested_mode,
            "research_effective_mode": decision.effective_mode,
            "research_release_status": decision.status,
            "research_release_reason": decision.reason,
            "research_compatibility_warnings": request.internal_research_warnings,
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
                research_provider=research_provider,
                research_provider_chain=research_provider_chain,
                max_steps=settings.max_steps,
                max_queries=settings.max_queries,
                max_sources=settings.max_sources,
                max_extracts=settings.max_extracts,
                search_cache_ttl_seconds=policy.search_cache_ttl_seconds,
                extraction_cache_ttl_seconds=policy.extraction_cache_ttl_seconds,
                hermes_planner_enabled=decision.use_hermes_planner,
                metadata={
                    "agent_mode": request.agent_mode,
                    "dry_run": request.dry_run,
                    "diagnostics_enabled": settings.show_diagnostics,
                    "research_release": decision.model_dump(mode="json"),
                    "research_compatibility_warnings": request.internal_research_warnings,
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


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, sort_keys=True)}\n\n"
