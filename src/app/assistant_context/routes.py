"""Browser-facing assistant context routes."""
from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.chat import ChatSessionStore, SendChatMessageRequest, SendChatMessageResponse, default_chat_store
from app.chat.generation_jobs import (
    chat_submission_lock,
    existing_chat_generation_turn,
    find_chat_generation_job,
    mark_chat_acceptance_failed,
    start_chat_generation_job,
)
from app.chat.research_citations import validate_completed_research_reply
from app.chat.research_jobs import link_user_message_to_research_job
from app.chat.research_release import apply_research_release_decision
from app.jobs import CreateJobRequest, InMemoryJobStore, JobRecord, ResourceClass, default_job_store
from app.jobs.research_inline import start_research_job
from app.research.contracts import RESEARCH_JOB_TYPE
from app.research.jobs import DeepResearchJobInput, create_deep_research_job_request
from app.research.planner import ResearchPlanner, ResearchPlanningBudget, ResearchPlanningRequest
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
_PLAN_UPDATE_ROUTE_NAME = "assistant_deep_research_plan_update_endpoint"
_PLAN_START_ROUTE_NAME = "assistant_deep_research_plan_start_endpoint"


class DeepResearchPlanUpdateRequest(BaseModel):
    max_pages: int = Field(ge=1, le=100)


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

    if _PLAN_UPDATE_ROUTE_NAME not in route_names:

        @app.patch(
            "/api/assistant/context/research/jobs/{job_id}/plan",
            response_model=JobRecord,
            include_in_schema=False,
            name=_PLAN_UPDATE_ROUTE_NAME,
        )
        async def update_deep_research_plan_endpoint(
            job_id: str,
            request: DeepResearchPlanUpdateRequest,
        ) -> JobRecord:
            job_store = job_store_factory()
            job = job_store.get_job(job_id)
            if job is None or job.type != RESEARCH_JOB_TYPE:
                raise HTTPException(status_code=404, detail="deep research job not found")
            try:
                input_payload = DeepResearchJobInput.model_validate(job.input_payload or {})
            except Exception as exc:
                raise HTTPException(status_code=409, detail="deep research plan is invalid") from exc
            if not input_payload.awaiting_plan_approval:
                raise HTTPException(status_code=409, detail="deep research has already started")
            settings = settings_factory()
            updated_input = input_payload.model_copy(
                update={
                    "max_sources": request.max_pages,
                    "max_queries": min(request.max_pages, settings.max_queries),
                    "max_extracts": min(request.max_pages, settings.max_extracts),
                }
            )
            updated_input = _with_research_plan(updated_input)
            updated = _update_job_input(job_store, job, updated_input)
            if updated is None:
                raise HTTPException(status_code=409, detail="deep research plan could not be updated")
            return updated

    if _PLAN_START_ROUTE_NAME not in route_names:

        @app.post(
            "/api/assistant/context/research/jobs/{job_id}/start",
            response_model=JobRecord,
            include_in_schema=False,
            name=_PLAN_START_ROUTE_NAME,
        )
        async def start_deep_research_plan_endpoint(job_id: str) -> JobRecord:
            job_store = job_store_factory()
            job = job_store.get_job(job_id)
            if job is None or job.type != RESEARCH_JOB_TYPE:
                raise HTTPException(status_code=404, detail="deep research job not found")
            try:
                input_payload = DeepResearchJobInput.model_validate(job.input_payload or {})
            except Exception as exc:
                raise HTTPException(status_code=409, detail="deep research plan is invalid") from exc
            if not input_payload.awaiting_plan_approval:
                return start_research_job(job_store, job)
            approved_input = input_payload.model_copy(update={"awaiting_plan_approval": False})
            updated = _update_job_input(
                job_store,
                job,
                approved_input,
                compat={**job.compat, "inline_execution": True},
            )
            if updated is None:
                raise HTTPException(status_code=409, detail="deep research plan could not be started")
            return start_research_job(job_store, updated)

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

        chat_store = chat_store_factory()
        send_request = _send_request(request)
        queued_context_diagnostics = {
            "web_research_mode": request.web_research_mode,
            "context_status": "queued_for_chat_generation",
            "research_requested_mode": decision.requested_mode,
            "research_effective_mode": decision.effective_mode,
            "research_release_status": decision.status,
            "research_release_reason": decision.reason,
            "research_release_warnings": decision.warnings,
        }
        job_store = job_store_factory()
        with chat_submission_lock(session_id, send_request.user_turn_id):
            existing_job = find_chat_generation_job(
                job_store,
                session_id=session_id,
                submission_id=send_request.user_turn_id,
            )
            if existing_job is not None:
                existing_turn = existing_chat_generation_turn(chat_store, existing_job)
                if existing_turn is not None:
                    session, user_message = existing_turn
                    return SendChatMessageResponse(
                        session=session,
                        user_message=user_message,
                        job=existing_job,
                    )
                raise HTTPException(
                    status_code=409,
                    detail="accepted chat submission is missing its user message",
                )
            appended = chat_store.begin_user_message(
                session_id,
                send_request,
                context_diagnostics=queued_context_diagnostics,
            )
            if appended is None:
                raise HTTPException(status_code=404, detail="chat session not found")
            session, user_message = appended
            try:
                job = job_store.create_job(
                    CreateJobRequest(
                        module="chatbot",
                        type="chat.generate",
                        resource_class=ResourceClass.GPU_LLM,
                        input_ref={"session_id": session.id, "message_id": user_message.id},
                        input_payload={
                            "session_id": session.id,
                            "message_id": user_message.id,
                            "submission_id": send_request.user_turn_id,
                            "provider_id": request.provider_id or session.provider_id,
                            "model_id": request.model_id or session.model_id,
                            "request": send_request.model_dump(mode="json"),
                            "context_status": "queued",
                            "research_release": decision.model_dump(mode="json"),
                            "research_compatibility_warnings": request.internal_research_warnings,
                        },
                        compat={
                            "contract": "assistant_context_chat_v1",
                            "inline_execution": True,
                        },
                    )
                )
            except Exception as exc:
                mark_chat_acceptance_failed(
                    chat_store,
                    session_id=session.id,
                    message_id=user_message.id,
                    error=exc,
                )
                raise HTTPException(
                    status_code=503,
                    detail="chat generation could not be queued",
                ) from exc

        def build_context() -> tuple[list[dict[str, Any]], dict[str, Any]]:
            context = context_service_factory().build(request)
            context_items = [item.model_dump(mode="json") for item in context.items]
            return context_items, {
                **context.diagnostics,
                "research_requested_mode": decision.requested_mode,
                "research_effective_mode": decision.effective_mode,
                "research_release_status": decision.status,
                "research_release_reason": decision.reason,
                "research_release_warnings": decision.warnings,
            }

        def finalize_context_chat(
            store: Any,
            completed_session_id: str,
            completed_message_id: str,
            context_items: list[dict[str, Any]],
            _context_diagnostics: dict[str, Any],
        ) -> None:
            validate_completed_research_reply(
                store,
                completed_session_id,
                completed_message_id,
                context_items,
                show_diagnostics=settings.show_diagnostics,
            )
            apply_research_release_decision(
                store,
                completed_session_id,
                completed_message_id,
                decision,
            )

        job = start_chat_generation_job(
            chat_store=chat_store,
            job_store=job_store,
            job=job,
            request=send_request,
            context_builder=build_context,
            completion_hook=finalize_context_chat,
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
    max_pages = _deep_research_page_limit(request, settings)
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
    research_input = _with_research_plan(
        DeepResearchJobInput(
            session_id=session.id,
            user_message_id=user_message.id,
            question=request.content,
            provider_id=request.provider_id or session.provider_id,
            model_id=request.model_id or session.model_id,
            research_provider=research_provider,
            research_provider_chain=research_provider_chain,
            max_steps=settings.max_steps,
            max_queries=min(max_pages, settings.max_queries),
            max_sources=max_pages,
            max_extracts=min(max_pages, settings.max_extracts),
            search_cache_ttl_seconds=policy.search_cache_ttl_seconds,
            extraction_cache_ttl_seconds=policy.extraction_cache_ttl_seconds,
            hermes_planner_enabled=decision.use_hermes_planner,
            awaiting_plan_approval=True,
            metadata={
                "agent_mode": request.agent_mode,
                "dry_run": request.dry_run,
                "diagnostics_enabled": settings.show_diagnostics,
                "research_release": decision.model_dump(mode="json"),
                "research_compatibility_warnings": request.internal_research_warnings,
            },
        )
    )
    job = job_store.create_job(create_deep_research_job_request(research_input))
    linked = link_user_message_to_research_job(
        chat_store,
        session.id,
        user_message.id,
        job.id,
    )
    if linked is not None:
        session, user_message = linked
    return SendChatMessageResponse(session=session, user_message=user_message, job=job)


def _deep_research_page_limit(
    request: AssistantContextChatRequest,
    settings: ResearchRuntimeSettings,
) -> int:
    selected = request.deep_research_max_pages
    value = settings.max_sources if selected is None else selected
    return max(1, min(100, int(value)))


def _with_research_plan(input_payload: DeepResearchJobInput) -> DeepResearchJobInput:
    budget = ResearchPlanningBudget(
        max_steps=input_payload.max_steps,
        max_queries=input_payload.max_queries,
        max_sources=input_payload.max_sources,
        max_extracts=input_payload.max_extracts,
    )
    decision = ResearchPlanner(
        prefer_hermes=input_payload.hermes_planner_enabled,
        provider_id=input_payload.provider_id,
        model_id=input_payload.model_id,
        use_provider=True,
    ).plan(
        ResearchPlanningRequest(question=input_payload.question, budget=budget)
    )
    metadata = {
        **input_payload.metadata,
        "planner_warnings": decision.warnings,
    }
    return input_payload.model_copy(
        update={
            "research_plan": decision.plan,
            "planner_backend": decision.backend,
            "metadata": metadata,
        }
    )


def _update_job_input(
    job_store: InMemoryJobStore,
    job: JobRecord,
    input_payload: DeepResearchJobInput,
    *,
    compat: dict[str, Any] | None = None,
) -> JobRecord | None:
    update = getattr(job_store, "update_job_input", None)
    if not callable(update):
        return None
    return update(
        job.id,
        input_payload.model_dump(mode="json"),
        compat=compat,
    )


def _send_request(request: AssistantContextChatRequest) -> SendChatMessageRequest:
    return SendChatMessageRequest(
        content=request.content,
        user_turn_id=request.user_turn_id,
        image_data_url=request.image_data_url,
        image_data_urls=request.image_data_urls,
        text_attachment=request.text_attachment,
        provider_id=request.provider_id,
        model_id=request.model_id,
        agent_mode=request.agent_mode,
        coding_approval_policy=request.coding_approval_policy,
        dry_run=request.dry_run,
        workspace_root=request.workspace_root,
        research_mode=request.web_research_mode,
    )


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, sort_keys=True)}\n\n"
