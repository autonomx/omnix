"""Previewing a portrait before it is a character's avatar (live portrait roadmap, Phase 4, "Setup").

``POST /api/tts/live-call/portrait-preview`` with an image asset, an emotion and the voice to speak with. The
gateway reads the image itself, has the portrait service prepare it (which checks the limits and finds the face;
a refusal comes back as its code, such as ``no_face``), speaks a short sample line with the live call's TTS and
has the service render it. The browser gets the audio (16-bit PCM, base64) and the frames (base64 JPEGs, 25 a
second) to play together. While a call streams, the portrait is busy and the preview says so.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.platform.live_voice.portrait.link import PortraitUnavailable, portrait_url, prepare_portrait, preview_portrait

logger = logging.getLogger(__name__)

PORTRAIT_PREVIEW_PATH = "/api/tts/live-call/portrait-preview"
SAMPLE_LINE = "Hello! This is how I will look when we talk."
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_PREVIEW_SECONDS = 8


class PortraitPreviewRequest(BaseModel):
    asset_id: str = Field(min_length=1, max_length=240)
    emotion: Literal["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"] = "neutral"
    speaker: str | None = Field(default=None, max_length=200)
    text: str = Field(default=SAMPLE_LINE, min_length=1, max_length=200)


class PortraitPreviewResponse(BaseModel):
    ok: bool
    code: str = ""
    message: str = ""
    sample_rate: int = 0
    audio: str = ""  # 16-bit little-endian mono PCM, base64
    fps: int = 25
    frames: list[str] = Field(default_factory=list)


def _read_image(asset_id: str) -> bytes:
    """The image, as the caller's tenant sees it (the asset store is tenant-scoped)."""
    from app.assets import AssetType, default_asset_store
    from app.assets.models import AssetContentTooLarge

    store = default_asset_store()
    asset = store.get_asset(asset_id)
    if asset is None or asset.type != AssetType.IMAGE:
        raise HTTPException(status_code=404, detail="image_not_found")
    try:
        return store.read_asset_bytes(asset_id, max_bytes=MAX_IMAGE_BYTES)
    except AssetContentTooLarge as exc:
        raise HTTPException(status_code=413, detail="image_too_large") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="image_not_found") from exc


def _speak(provider: Any, text: str, speaker: str | None) -> tuple[bytes, int]:
    """The sample line in the live call's voice: 16-bit PCM at the provider's rate, at most a few seconds."""
    from app.conversation.tts_stream_contract import audio_chunk_to_pcm16_bytes

    chunks, rate = [], 24_000
    for audio_chunk, sample_rate, _timing in provider.generate_audio_stream(text=text, speaker=speaker,
                                                                             language="English"):
        rate = int(sample_rate or rate)
        chunks.append(audio_chunk_to_pcm16_bytes(audio_chunk))
        if sum(len(chunk) for chunk in chunks) >= MAX_PREVIEW_SECONDS * rate * 2:
            break
    return b"".join(chunks)[: MAX_PREVIEW_SECONDS * rate * 2], rate


def register_portrait_preview_route(router: APIRouter, *, provider_factory: Any) -> None:
    @router.post(PORTRAIT_PREVIEW_PATH, response_model=PortraitPreviewResponse, tags=["live-voice"])
    async def portrait_preview(request: PortraitPreviewRequest) -> PortraitPreviewResponse:
        base_url = portrait_url()
        if not base_url:
            return PortraitPreviewResponse(ok=False, code="portrait_not_configured",
                                           message="The portrait service is not set up")
        image = await asyncio.to_thread(_read_image, request.asset_id)
        from app.runtime.tenant_context import current_tenant

        try:
            latent_key = await prepare_portrait(base_url, current_tenant().workspace_id, image)
            provider = await asyncio.to_thread(provider_factory)
            if provider is None or not hasattr(provider, "generate_audio_stream"):
                return PortraitPreviewResponse(ok=False, code="tts_unavailable", message="No voice is available")
            pcm, rate = await asyncio.to_thread(_speak, provider, request.text, request.speaker)
            frames = await preview_portrait(base_url, latent_key, request.emotion, pcm, rate)
        except PortraitUnavailable as exc:
            return PortraitPreviewResponse(ok=False, code=exc.code, message=str(exc))
        return PortraitPreviewResponse(ok=True, sample_rate=rate, audio=base64.b64encode(pcm).decode("ascii"),
                                       frames=frames)


__all__ = ["PORTRAIT_PREVIEW_PATH", "PortraitPreviewRequest", "PortraitPreviewResponse",
           "register_portrait_preview_route"]
