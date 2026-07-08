"""Browser-facing routes for per-session Chat memory snapshots."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, HTTPException

from app.chat import ChatSessionStore, default_chat_store
from app.chat.memory_session import (
    RefreshSessionMemoryRequest,
    SessionMemoryConflictError,
    SessionMemoryState,
    get_session_memory_state,
    refresh_session_memory,
)

from .service import MemoryService, default_memory_service

_GET_ROUTE_NAME = "assistant_memory_session_state_endpoint"
_REFRESH_ROUTE_NAME = "assistant_memory_session_refresh_endpoint"


def register_assistant_memory_routes(
    app: FastAPI,
    *,
    chat_store_factory: Callable[[], ChatSessionStore] = default_chat_store,
    memory_service_factory: Callable[[], MemoryService] = default_memory_service,
) -> None:
    route_names = {getattr(route, "name", "") for route in app.routes}
    if _GET_ROUTE_NAME not in route_names:

        @app.get(
            "/api/chat/sessions/{session_id}/memory",
            response_model=SessionMemoryState,
            tags=["chat-memory"],
            include_in_schema=False,
            name=_GET_ROUTE_NAME,
        )
        async def assistant_memory_session_state_endpoint(
            session_id: str,
        ) -> SessionMemoryState:
            state = get_session_memory_state(
                chat_store_factory(),
                memory_service_factory(),
                session_id,
            )
            if state is None:
                raise HTTPException(status_code=404, detail="chat session not found")
            return state

    if _REFRESH_ROUTE_NAME not in route_names:

        @app.post(
            "/api/chat/sessions/{session_id}/memory/refresh",
            response_model=SessionMemoryState,
            tags=["chat-memory"],
            include_in_schema=False,
            name=_REFRESH_ROUTE_NAME,
        )
        async def assistant_memory_session_refresh_endpoint(
            session_id: str,
            request: RefreshSessionMemoryRequest,
        ) -> SessionMemoryState:
            try:
                state = refresh_session_memory(
                    chat_store_factory(),
                    memory_service_factory(),
                    session_id,
                    request,
                )
            except SessionMemoryConflictError as exc:
                raise HTTPException(
                    status_code=409,
                    detail={"code": "memory_snapshot_revision_conflict", "message": str(exc)},
                ) from exc
            if state is None:
                raise HTTPException(status_code=404, detail="chat session not found")
            return state
