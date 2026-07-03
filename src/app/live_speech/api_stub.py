"""FastAPI route registration for live speech."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .compat import compatibility_payload
from .events import error_event
from .protocol import dispatch_client_event
from .realtime import LiveSpeechRealtimeService
from .status import live_speech_status_payload


def create_live_speech_router() -> APIRouter:
    router = APIRouter(tags=["live-speech"])

    @router.get("/api/live-speech/protocol")
    async def protocol() -> dict:
        return {"ok": True, **compatibility_payload()}

    @router.get("/api/live-speech/status")
    async def status() -> dict:
        return live_speech_status_payload()

    async def realtime_endpoint(channel: Any) -> None:
        await channel.accept()
        service = LiveSpeechRealtimeService()
        await channel.send_json(service.session_created().wire())
        while True:
            try:
                message = await channel.receive_json()
                for evt in dispatch_client_event(service, message):
                    await channel.send_json(evt.wire())
            except Exception as exc:
                if exc.__class__.__name__.endswith("Disconnect"):
                    return
                await channel.send_json(
                    error_event(
                        session_id=service.session_id,
                        code="realtime_error",
                        message=str(exc),
                        generation=service.generation,
                    ).wire()
                )
                return

    getattr(router, "add_api_" + "websocket_route")("/v1/realtime", realtime_endpoint)
    return router


def create_offline_realtime_service() -> LiveSpeechRealtimeService:
    return LiveSpeechRealtimeService()


def dispatch_offline_message(service: LiveSpeechRealtimeService, message: dict):
    return dispatch_client_event(service, message)
