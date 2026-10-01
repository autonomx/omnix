"""Core chat routes with explicitly injected store factories."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.chat.generation_jobs import (
    chat_submission_lock,
    existing_chat_generation_turn,
    find_chat_generation_job,
    interrupt_active_chat_generation_jobs,
    mark_chat_acceptance_failed,
    start_chat_generation_job,
)
from app.chat.models import (
    ChatSession,
    ChatSessionListResponse,
    CreateChatSessionRequest,
    DeleteChatSessionResponse,
    SendChatMessageRequest,
    SendChatMessageResponse,
)
from app.jobs.models import CreateJobRequest, ResourceClass
from app.live_voice.transport.sse import OmnixStreamingResponse


def _chat_message_image_data_urls(metadata: object) -> list[str]:
    if not isinstance(metadata, dict):
        return []
    values: list[str] = []
    raw = metadata.get("image_data_urls")
    if isinstance(raw, list):
        values.extend(value for value in raw if isinstance(value, str) and value)
    legacy = metadata.get("image_data_url")
    if isinstance(legacy, str) and legacy:
        values.insert(0, legacy)
    return list(dict.fromkeys(values))


def register_core_chat_routes(router: APIRouter, *, get_chat_store, get_job_store):
    @router.get(
        "/api/chat/sessions", response_model=ChatSessionListResponse, tags=["chat"]
    )
    def chat_sessions(
        limit: int = Query(default=100, ge=1, le=100),
        cursor: str | None = Query(default=None, max_length=512),
    ) -> ChatSessionListResponse:
        try:
            return get_chat_store().list_sessions(limit=limit, cursor=cursor)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @router.post("/api/chat/sessions", response_model=ChatSession, tags=["chat"])
    def create_chat_session(request: CreateChatSessionRequest) -> ChatSession:
        return get_chat_store().create_session(request)

    @router.get(
        "/api/chat/sessions/{session_id}", response_model=ChatSession, tags=["chat"]
    )
    def chat_session(
        session_id: str,
        include_attachments: bool = Query(default=True),
    ) -> ChatSession:
        chat_store = get_chat_store()
        if include_attachments:
            session = chat_store.get_session(session_id)
        else:
            get_session_without_attachments = getattr(
                chat_store, "get_session_without_attachments", None
            )
            session = (
                get_session_without_attachments(session_id)
                if callable(get_session_without_attachments)
                else chat_store.get_session(session_id)
            )
        if session is None:
            raise HTTPException(status_code=404, detail="chat session not found")
        return session

    @router.get(
        "/api/chat/sessions/{session_id}/attachments",
        response_model=dict[str, list[str]],
        tags=["chat"],
    )
    def chat_session_attachments(session_id: str) -> dict[str, list[str]]:
        chat_store = get_chat_store()
        get_session_attachments = getattr(chat_store, "get_session_attachments", None)
        if callable(get_session_attachments):
            attachments = get_session_attachments(session_id)
        else:
            session = chat_store.get_session(session_id)
            attachments = (
                {
                    message.id: _chat_message_image_data_urls(message.metadata)
                    for message in session.messages
                    if _chat_message_image_data_urls(message.metadata)
                }
                if session is not None
                else None
            )
        if attachments is None:
            raise HTTPException(status_code=404, detail="chat session not found")
        return attachments

    @router.delete(
        "/api/chat/sessions/{session_id}",
        response_model=DeleteChatSessionResponse,
        tags=["chat"],
    )
    def delete_chat_session(session_id: str) -> DeleteChatSessionResponse:
        if not get_chat_store().delete_session(session_id):
            raise HTTPException(status_code=404, detail="chat session not found")
        return DeleteChatSessionResponse(session_id=session_id)

    @router.post(
        "/api/chat/sessions/{session_id}/messages",
        response_model=SendChatMessageResponse,
        tags=["chat"],
    )
    def send_chat_message(
        session_id: str, request: SendChatMessageRequest
    ) -> SendChatMessageResponse:
        chat_store = get_chat_store()
        job_store = get_job_store()
        with chat_submission_lock(
            session_id, request.user_turn_id, job_store=job_store, chat_store=chat_store
        ):
            existing_job = find_chat_generation_job(
                job_store,
                session_id=session_id,
                submission_id=request.user_turn_id,
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
            interrupt_active_chat_generation_jobs(
                chat_store,
                job_store,
                session_id=session_id,
                reason="Interrupted by a newer Chat prompt.",
            )
            appended = chat_store.begin_user_message(session_id, request)
            if appended is None:
                raise HTTPException(status_code=404, detail="chat session not found")
            session, user_message = appended
            try:
                job = job_store.create_job(
                    CreateJobRequest(
                        module="chatbot",
                        type="chat.generate",
                        resource_class=ResourceClass.GPU_LLM,
                        input_ref={
                            "session_id": session.id,
                            "message_id": user_message.id,
                        },
                        input_payload={
                            "session_id": session.id,
                            "message_id": user_message.id,
                            "submission_id": request.user_turn_id,
                            "provider_id": request.provider_id or session.provider_id,
                            "model_id": request.model_id or session.model_id,
                            "request": request.model_dump(mode="json"),
                        },
                        compat={
                            "contract": "chat_session_v1",
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
        job = start_chat_generation_job(
            chat_store=chat_store,
            job_store=job_store,
            job=job,
            request=request,
        )
        return SendChatMessageResponse(
            session=session, user_message=user_message, job=job
        )

    @router.post(
        "/api/chat/sessions/{session_id}/messages/stream",
        response_model=None,
        response_class=OmnixStreamingResponse,
        responses={
            200: {
                "description": "Chat generation events as Server-Sent Events.",
                "content": {"text/event-stream": {"schema": {"type": "string"}}},
            }
        },
        tags=["chat"],
    )
    async def stream_chat_message(
        session_id: str, request: SendChatMessageRequest
    ) -> OmnixStreamingResponse:
        chat_store = get_chat_store()
        begin_streaming = getattr(chat_store, "begin_streaming_user_message", None)
        begin_user_message = (
            begin_streaming if callable(begin_streaming) else chat_store.begin_user_message
        )
        appended = await asyncio.to_thread(begin_user_message, session_id, request)
        if appended is None:
            raise HTTPException(status_code=404, detail="chat session not found")
        session, user_message = appended

        def generate():
            yield f"data: {json.dumps({'type': 'user_message', 'message': user_message.model_dump(mode='json')}, sort_keys=True)}\n\n"
            content = ""
            metadata: dict[str, Any] = {"generation_status": "completed"}
            completed = None
            reply_persisted = False
            try:
                for event in chat_store.stream_provider_reply_chunks(
                    session,
                    user_message,
                    provider_id=request.provider_id or session.provider_id,
                    model_id=request.model_id or session.model_id,
                ):
                    if event.get("type") == "complete":
                        content = str(event.get("content") or "").strip()
                        metadata = (
                            event.get("metadata")
                            if isinstance(event.get("metadata"), dict)
                            else metadata
                        )
                        # Persist at the provider completion boundary, before the
                        # completion event is yielded. Live voice playback can
                        # outlast LLM generation and a later barge-in may close
                        # the HTTP body before the session footer is requested.
                        completed = chat_store.complete_streamed_reply(
                            session.id,
                            user_message.id,
                            content,
                            metadata,
                        )
                        reply_persisted = True
                    yield f"data: {json.dumps(event, sort_keys=True)}\n\n"
                if not reply_persisted:
                    completed = chat_store.complete_streamed_reply(
                        session.id,
                        user_message.id,
                        content,
                        metadata,
                    )
                if completed is not None:
                    yield f"data: {json.dumps({'type': 'session', 'session': completed.model_dump(mode='json')}, sort_keys=True)}\n\n"
                yield f"data: {json.dumps({'type': 'done'}, sort_keys=True)}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc) or 'Chat stream failed.'}, sort_keys=True)}\n\n"

        user_turn_id = str(request.user_turn_id or "").strip() or None
        speech_segment_id = str(request.speech_segment_id or "").strip() or None
        voice_turn_id = (
            user_turn_id.removeprefix("voice-user-turn:")
            if user_turn_id and user_turn_id.startswith("voice-user-turn:")
            else None
        )
        return OmnixStreamingResponse(
            generate(),
            media_type="text/event-stream",
            eager_sync=True,
            diagnostic_context={
                "route_path": "/api/chat/sessions/{session_id}/messages/stream",
                "session_id": session_id,
                "user_turn_id": user_turn_id,
                "speech_segment_id": speech_segment_id,
                "voice_turn_id": voice_turn_id,
            },
        )
