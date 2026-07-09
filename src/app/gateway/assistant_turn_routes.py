"""Authoritative assistant-turn cancellation routes."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.chat.assistant_turns import AssistantTurnRecord, default_assistant_turn_coordinator

_ROUTE_SENTINEL = "_omnix_assistant_turn_routes_registered"
_HOOK_SENTINEL = "_omnix_assistant_turn_routes_hook_installed"


class CancelAssistantTurnRequest(BaseModel):
    reason: str = Field(default="user_interruption", min_length=1, max_length=240)


class CancelAssistantTurnResponse(BaseModel):
    ok: bool = True
    turn: AssistantTurnRecord


def register_assistant_turn_routes(gateway: FastAPI) -> None:
    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return
    setattr(gateway.state, _ROUTE_SENTINEL, True)

    @gateway.get("/api/chat/assistant-turns/{assistant_turn_id}", response_model=AssistantTurnRecord, tags=["chat"])
    async def assistant_turn_status(assistant_turn_id: str) -> AssistantTurnRecord:
        record = default_assistant_turn_coordinator().get(assistant_turn_id)
        if record is None:
            raise HTTPException(status_code=404, detail="assistant turn not found")
        return record

    @gateway.post(
        "/api/chat/assistant-turns/{assistant_turn_id}/cancel",
        response_model=CancelAssistantTurnResponse,
        tags=["chat"],
    )
    async def cancel_assistant_turn(
        assistant_turn_id: str,
        request: CancelAssistantTurnRequest,
    ) -> CancelAssistantTurnResponse:
        record = default_assistant_turn_coordinator().request_cancel(assistant_turn_id, request.reason)
        if record is None:
            raise HTTPException(status_code=404, detail="assistant turn not found")
        return CancelAssistantTurnResponse(turn=record)


def install_assistant_turn_route_hook() -> None:
    """Install route registration before the gateway app is constructed."""
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (args and args[0] == "Omnix Web Gateway"):
            register_assistant_turn_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
