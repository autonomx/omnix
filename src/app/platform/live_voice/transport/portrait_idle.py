"""A group call's members who are not speaking stay live (companion 5.5): each plays its portrait's idle loop.

``GET /api/tts/live-call/portrait-idle?session_id=&speaker_id=`` gives a member's idle loop and blink twins (base64
JPEGs, ``frame_ms`` apart); no ``speaker_id`` is the chat's own character. The browser names the member; code checks
the seat (``speaker_view``) and reads the portrait image itself, as the avatar websocket does. The portrait service
renders a loop only while no call streams: during a call a member with no loop yet is refused with ``portrait_busy``,
and the browser keeps that member's picture until its own turn brings its loop.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.platform.characters.contracts import default_character_avatar_service, resolve_live_call_runtime
from app.platform.live_voice.portrait.link import PortraitUnavailable, idle_portrait, portrait_url, prepare_portrait
from app.platform.live_voice.transport.avatar_websocket import MAX_PORTRAIT_BYTES, _load_session, _speaker_session

logger = logging.getLogger(__name__)

PORTRAIT_IDLE_PATH = "/api/tts/live-call/portrait-idle"


class PortraitIdleResponse(BaseModel):
    ok: bool
    code: str = ""
    message: str = ""
    frame_ms: int = 0
    idle: list[str] = Field(default_factory=list)
    blink: list[str] = Field(default_factory=list)


def _refused(code: str, message: str) -> PortraitIdleResponse:
    return PortraitIdleResponse(ok=False, code=code, message=message)


def _member_runtime(chat_store_factory: Callable[[], Any], session_id: str, speaker_id: str) -> Any:
    """The live-call runtime as the named member sees it; None when the chat is not the caller's or the member is
    not on its call."""
    session = _load_session(chat_store_factory, session_id)
    if session is not None and speaker_id:
        session = _speaker_session(session, speaker_id)
    return resolve_live_call_runtime(session) if session is not None else None


def register_portrait_idle_route(router: APIRouter, *, chat_store_factory: Callable[[], Any]) -> None:
    @router.get(PORTRAIT_IDLE_PATH, response_model=PortraitIdleResponse, tags=["live-voice"])
    async def portrait_idle(session_id: str = Query(min_length=1, max_length=200),  # noqa: B008
                            speaker_id: str = Query("", max_length=200)) -> PortraitIdleResponse:  # noqa: B008
        base_url = portrait_url()
        if not base_url:
            return _refused("portrait_not_configured", "The portrait service is not set up")
        runtime = await asyncio.to_thread(_member_runtime, chat_store_factory, session_id, speaker_id.strip())
        if runtime is None:
            return _refused("speaker_not_on_call", "That character is not on this call")
        pack = runtime.avatar_pack
        if pack is None or pack.renderer != "portrait":
            return _refused("not_a_portrait", "This character's avatar is not a portrait")
        from app.runtime.tenant_context import current_tenant

        try:
            image = await asyncio.to_thread(default_character_avatar_service().portrait_image, pack,
                                            max_bytes=MAX_PORTRAIT_BYTES)
            latent_key = await prepare_portrait(base_url, current_tenant().workspace_id, image)
            loop = await idle_portrait(base_url, latent_key)
        except PortraitUnavailable as exc:
            return _refused(exc.code, str(exc) or "The portrait is not available")
        except Exception:  # noqa: BLE001 - the member keeps its picture
            logger.warning("Portrait idle loop could not be read for session %s", session_id, exc_info=True)
            return _refused("portrait_failed", "The portrait could not be read")
        return PortraitIdleResponse(ok=True, frame_ms=loop.frame_ms, idle=loop.idle, blink=loop.blink)


__all__ = ["PORTRAIT_IDLE_PATH", "PortraitIdleResponse", "register_portrait_idle_route"]
