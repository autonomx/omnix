"""Feature-owned per-session rich-replies route (chat generative UI, GUI-3.1)."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException

from .models import ChatRichRepliesResponse, UpdateChatRichRepliesRequest
from .rich_replies import update_conversation_rich_replies


def create_rich_replies_router(*, chat_store_factory: Callable[[], Any]) -> APIRouter:
    router = APIRouter()

    @router.post("/api/chat/sessions/{session_id}/rich-replies", response_model=ChatRichRepliesResponse)
    def set_conversation_rich_replies(
        session_id: str,
        request: UpdateChatRichRepliesRequest,
    ) -> ChatRichRepliesResponse:
        session = update_conversation_rich_replies(chat_store_factory(), session_id, request.rich_replies)
        if session is None:
            raise HTTPException(status_code=404, detail="chat_session_not_found")
        return ChatRichRepliesResponse(session_id=session.id, rich_replies=session.rich_replies)

    return router
