"""Conversation research-mode routes for the web gateway."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI, HTTPException

from app.chat import UpdateChatResearchModeRequest, default_chat_store
from app.chat.research_mode import update_conversation_research_mode

_ROUTE_SENTINEL = "_omnix_research_mode_routes_registered"
_HOOK_SENTINEL = "_omnix_research_mode_routes_hook_installed"


def register_research_mode_routes(gateway: FastAPI) -> None:
    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return
    setattr(gateway.state, _ROUTE_SENTINEL, True)

    @gateway.post(
        "/api/chat/sessions/{session_id}/research-mode",
        include_in_schema=False,
    )
    def set_conversation_research_mode(
        session_id: str,
        request: UpdateChatResearchModeRequest,
    ) -> dict[str, Any]:
        session = update_conversation_research_mode(
            default_chat_store(),
            session_id,
            request.research_mode_override,
        )
        if session is None:
            raise HTTPException(status_code=404, detail="chat_session_not_found")
        return {
            "ok": True,
            "session_id": session.id,
            "research_mode_override": session.research_mode_override,
        }


def install_research_mode_route_hook() -> None:
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        title = kwargs.get("title") or (args[0] if args else "")
        if title == "Omnix Web Gateway":
            register_research_mode_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
