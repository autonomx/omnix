"""Browser-facing assistant context routes."""
from __future__ import annotations

import asyncio
from collections.abc import Callable

from fastapi import FastAPI, HTTPException

from app.chat import ChatSessionStore, SendChatMessageRequest, SendChatMessageResponse, default_chat_store
from app.jobs import CreateJobRequest, ResourceClass, SQLiteJobStore, default_job_store

from .models import AssistantContextChatRequest
from .service import AssistantContextService, default_assistant_context_service

_ROUTE_NAME = "assistant_context_chat_message_endpoint"


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
        context = await asyncio.to_thread(context_service_factory().build, request)
        send_request = SendChatMessageRequest(
            content=request.content,
            provider_id=request.provider_id,
            model_id=request.model_id,
            agent_mode=request.agent_mode,
            dry_run=request.dry_run,
        )
        appended = chat_store_factory().append_user_message(
            session_id,
            send_request,
            context_items=[item.model_dump(mode="json") for item in context.items],
            context_diagnostics=context.diagnostics,
        )
        if appended is None:
            raise HTTPException(status_code=404, detail="chat session not found")
        session, user_message = appended
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
