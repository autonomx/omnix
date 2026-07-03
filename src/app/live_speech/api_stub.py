"""FastAPI route registration for live speech."""
from __future__ import annotations

from fastapi import APIRouter

from .protocol import dispatch_client_event
from .realtime import LiveSpeechRealtimeService


def create_live_speech_router() -> APIRouter:
    router = APIRouter(tags=["live-speech"])

    @router.get("/api/live-speech/protocol")
    async def protocol() -> dict:
        return {"ok": True, "socket_path": "/v1/realtime", "contract": "omnix_live_speech_realtime_v1"}

    return router


def create_offline_realtime_service() -> LiveSpeechRealtimeService:
    return LiveSpeechRealtimeService()


def dispatch_offline_message(service: LiveSpeechRealtimeService, message: dict):
    return dispatch_client_event(service, message)
