"""Route registration placeholder for live speech."""
from __future__ import annotations

from fastapi import APIRouter


def create_live_speech_router() -> APIRouter:
    return APIRouter(tags=["live-speech"])
