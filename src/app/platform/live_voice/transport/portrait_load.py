"""Loading the portrait model before a call, from the call panel's button (live portrait roadmap, D-9).

The model loads on demand when a call first asks for it; this asks ahead of the call, so the video is there when it
starts. ``POST /api/tts/live-call/portrait-load`` with the portrait's image asset has the service prepare it, which
starts a load when none is under way and renders the portrait's idle loop, so ``ready`` means a call has no rendering
left to wait for; the browser asks again while the answer is ``loading``. The service's own checks
apply as they do to a call: with too little memory it refuses (``model_busy``). ``GET
/api/tts/live-call/portrait-load`` says where the model stands, since it unloads after an idle while.
"""
from __future__ import annotations

from typing import Literal

import asyncio
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.platform.live_voice.portrait.link import PortraitUnavailable, portrait_health, portrait_url, prepare_portrait
from app.platform.live_voice.transport.portrait_preview import _read_image

PORTRAIT_LOAD_PATH = "/api/tts/live-call/portrait-load"
# The load is under way, or the service is restarting after an idle unload: asking again will tell.
STILL_LOADING = frozenset({"warming", "service_unreachable"})


class PortraitLoadRequest(BaseModel):
    asset_id: str = Field(min_length=1, max_length=240)


class PortraitLoadResponse(BaseModel):
    status: Literal["ready", "loading", "unavailable"]
    code: str = ""
    message: str = ""


class PortraitModelStatus(BaseModel):
    status: Literal["ready", "loading", "unloaded", "unavailable"]


def register_portrait_load_routes(router: APIRouter) -> None:
    @router.post(PORTRAIT_LOAD_PATH, response_model=PortraitLoadResponse, tags=["live-voice"])
    async def portrait_load(request: PortraitLoadRequest) -> PortraitLoadResponse:
        base_url = portrait_url()
        if not base_url:
            return PortraitLoadResponse(status="unavailable", code="portrait_not_configured",
                                        message="The portrait service is not set up")
        image = await asyncio.to_thread(_read_image, request.asset_id)
        from app.runtime.tenant_context import current_tenant

        try:
            await prepare_portrait(base_url, current_tenant().workspace_id, image)
        except PortraitUnavailable as exc:
            status = "loading" if exc.code in STILL_LOADING else "unavailable"
            return PortraitLoadResponse(status=status, code=exc.code, message=str(exc))
        return PortraitLoadResponse(status="ready")

    @router.get(PORTRAIT_LOAD_PATH, response_model=PortraitModelStatus, tags=["live-voice"])
    async def portrait_model_status() -> PortraitModelStatus:
        base_url = portrait_url()
        if not base_url:
            return PortraitModelStatus(status="unavailable")
        state = await portrait_health(base_url)
        return PortraitModelStatus(status="ready" if state == "ready" else "loading" if state == "warming" else "unloaded")


__all__ = ["PORTRAIT_LOAD_PATH", "PortraitLoadRequest", "PortraitLoadResponse", "PortraitModelStatus",
           "register_portrait_load_routes"]
