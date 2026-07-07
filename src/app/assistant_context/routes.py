"""Browser-facing assistant context routes."""
from __future__ import annotations

import asyncio
from collections.abc import Callable

from fastapi import FastAPI, HTTPException

from app.chat import ChatSessionStore, SendChatMessageRequest, SendChatMessageResponse, default_chat_store
from app.chat.research_citations import validate_completed_research_reply
from app.jobs import CreateJobRequest, JobStatus, ResourceClass, SQLiteJobStore, default_job_store
from app.research.contracts import RESEARCH_JOB_TYPE
from app.research.jobs import DeepResearchJobInput, create_deep_research_job_request

from .models import AssistantContextChatRequest
from .service import AssistantContextService, default_assistant_context_service

_ROUTE_NAME = "assistant_context_chat_message_endpoint"
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
) -> None:
    if any(getattr(route, "name", "") == _ROUTE_NAME for route in app.routes):
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
        if request.web_research_mode == "deep":
            return _begin_deep_research(
                session_id,
                request,
                chat_store=chat_store_factory(),
                job_store=job_store_factory(),
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
) -> SendChatMessageResponse:
    active = next(
        (
            job
            for job in job_store.list_jobs()
            if job.type == RESEARCH_JOB_TYPE
            and job.owner_id == session_id
            and job.status in _ACTIVE_RESEARCH_STATUSES
        ),
        None,
    )
    if active is not None:
        raise HTTPException(status_code=409, detail="deep_research_already_active")

    appended = chat_store.begin_user_message(
        session_id,
        _send_request(request),
        context_diagnostics={
            "web_research_mode": "deep",
            "web_search_status": "queued_as_durable_research_job",
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
                metadata={"agent_mode": request.agent_mode, "dry_run": request.dry_run},
            )
        )
    )
    user_message.metadata.update(
        {
            "research_mode": "deep",
            "research_status": "queued",
            "research_job_id": job.id,
        }
    )
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
