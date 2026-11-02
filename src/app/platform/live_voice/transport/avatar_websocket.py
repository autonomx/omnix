"""The live call's portrait websocket (docs/architecture/OMNIX_LIVE_PORTRAIT_ROADMAP.md, Phase 2).

``/api/tts/live-call/avatar-websocket?token=...&session_id=...``: the browser opens it with the avatar token
from the TTS websocket's ``hello``. The token is accepted only from the principal it was issued to, while its
TTS connection is open on this gateway. The gateway then resolves the session's character and avatar pack,
reads the portrait image itself (never from the browser), prepares it on the portrait service, opens the
call's portrait link and attaches it to the TTS connection, which starts copying the call's audio.

To the browser: ``{"type": "ready", "fallback_renderer": ...}``, then frames as binary messages exactly as the
service sends them (``app.conversation.portrait_stream_contract``: a header with the output, epoch, segment and
offset, then a JPEG; the idle loop's frames first). When the portrait cannot serve,
``{"type": "unavailable", "code", "message"}`` and the socket closes; the browser shows the pack's fallback
renderer. The portrait model loads on demand (about a minute, on the first call after the service started): while it
does, ``{"type": "loading"}`` goes to the browser, which shows the fallback, and the gateway asks again every 2 s
until it is ready (up to three minutes). When the machine has too little memory for the load, it is
``{"type": "loading", "code": "model_busy"}`` and the gateway keeps asking, more slowly, for as long as the call
lasts: the portrait starts once memory is freed. From the browser, every 250 ms: ``frame_ack`` with the segment and offset it is playing (the play
position the service's phrase-end deadlines use), the speech frames it has ``received``, how many came ``late``
and its average ``decode_ms``. Those step the call's quality level (``portrait/quality.py``); a change goes to
the service and, as ``{"type": "quality", "level"}``, to the browser.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import math
import time
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.conversation.portrait_stream_contract import PortraitMessageError, unpack

from app.platform.characters.contracts import (
    default_character_avatar_service,
    portrait_emotion_label,
    resolve_live_call_runtime,
)
from app.platform.live_voice.portrait.calls import PortraitCalls, principal_id
from app.platform.live_voice.portrait.link import PortraitLink, PortraitUnavailable, portrait_url, prepare_portrait
from app.platform.live_voice.portrait.quality import QualityController, starting_level

logger = logging.getLogger(__name__)

AVATAR_WEBSOCKET_PATH = "/api/tts/live-call/avatar-websocket"
MAX_PORTRAIT_BYTES = 12 * 1024 * 1024
LINK_CHECK_SECONDS = 0.5
LOAD_WAIT_SECONDS = 180.0
LOAD_POLL_SECONDS = 2.0
# Too little memory to load can last the whole call; each ask sends the portrait's image.
MEMORY_POLL_SECONDS = 5.0
# The service restarts itself after an idle unload (a few seconds without it).
RESTART_WAIT_SECONDS = 20.0
# The service's refusal when VRAM or host commit cannot take the load (services.portrait.portrait_server).
MEMORY_SHORT = "model_busy"
# Above any offset or frame count a call reaches (about 12 hours of 48 kHz samples).
MAX_ACK_COUNT = 2**31


def _load_session(chat_store_factory: Callable[[], Any], session_id: str) -> Any:
    """The session, as the caller's tenant sees it (None when it is not theirs)."""
    return chat_store_factory().get_session(session_id)


async def _unavailable(websocket: WebSocket, code: str, message: str) -> None:
    with contextlib.suppress(WebSocketDisconnect, RuntimeError):  # the browser may have left while this was decided
        await websocket.send_json({"type": "unavailable", "code": code, "message": message})
        await websocket.close(code=4001, reason=code)


def _worth_waiting(code: str, waited: float) -> bool:
    """Whether a refusal may pass on its own. Too little memory is worth waiting out for as long as the call lasts."""
    if code == MEMORY_SHORT:
        return True
    return ((code == "warming" and waited < LOAD_WAIT_SECONDS)
            or (code == "service_unreachable" and waited < RESTART_WAIT_SECONDS))


async def _prepare_when_loaded(websocket: WebSocket, base_url: str, tenant: str, image: bytes,
                               call_open: Callable[[], bool]) -> str | None:
    """The portrait's latent key, once its model has loaded; None when the browser left, or the call ended, while it
    loaded. The service is asked again at a steady pace whatever the browser sends meanwhile, and each kind of wait
    gets its full time however long the one before it took."""
    started = time.monotonic()
    waiting_for: str | None = None
    told: dict[str, str] | None = None
    while True:
        try:
            return await prepare_portrait(base_url, tenant, image)
        except PortraitUnavailable as exc:
            if exc.code != waiting_for:
                waiting_for, started = exc.code, time.monotonic()
            if not _worth_waiting(exc.code, time.monotonic() - started):
                raise
        short = waiting_for == MEMORY_SHORT
        status = {"type": "loading", "code": MEMORY_SHORT} if short else {"type": "loading"}
        if status != told:
            try:
                await websocket.send_json(status)
            except WebSocketDisconnect:
                return None
            told = status
        poll_at = time.monotonic() + (MEMORY_POLL_SECONDS if short else LOAD_POLL_SECONDS)
        while (left := poll_at - time.monotonic()) > 0:
            try:
                await asyncio.wait_for(websocket.receive_text(), left)  # anything sent meanwhile is ignored
            except asyncio.TimeoutError:
                break
            except WebSocketDisconnect:
                return None
        if not call_open():
            return None


def _count(value: Any) -> int:
    """A non-negative count from the browser (ValueError for one that is not)."""
    number = float(value or 0)
    if not math.isfinite(number) or number < 0 or number > MAX_ACK_COUNT:
        raise ValueError("not a count")
    return int(number)


def _finite(value: Any) -> float:
    """A non-negative, finite measure from the browser (ValueError for one that is not)."""
    number = float(value or 0.0)
    if not math.isfinite(number) or number < 0:
        raise ValueError("not a finite measure")
    return number


def _is_speech_frame(message: bytes) -> bool:
    """Whether a frame is the call's speech: not the idle loop's burst at the start (with its blink), nor a reply's
    frames back to it (the browser counts none of them as received speech, so none is counted in flight)."""
    try:
        header, _ = unpack(message)
    except PortraitMessageError:
        return False
    return header.get("output_id") not in ("idle", "blink", "transition")


def register_live_call_avatar_websocket(router: APIRouter, calls: PortraitCalls, *,
                                        chat_store_factory: Callable[[], Any]) -> None:
    @router.websocket(AVATAR_WEBSOCKET_PATH)
    async def live_call_avatar_websocket(websocket: WebSocket) -> None:
        await websocket.accept()
        token = websocket.query_params.get("token", "")
        session_id = websocket.query_params.get("session_id", "")
        principal = principal_id(websocket.scope)
        call = calls.claim(token, principal) if token else None
        if call is None or not session_id:
            await websocket.close(code=1008, reason="invalid_avatar_token")
            return
        base_url = portrait_url()
        if not base_url:
            await _unavailable(websocket, "portrait_not_configured", "The portrait service is not set up")
            return
        try:
            session = await asyncio.to_thread(_load_session, chat_store_factory, session_id)
            runtime = await asyncio.to_thread(resolve_live_call_runtime, session) if session is not None else None
        except Exception:  # noqa: BLE001 - the call goes on without a portrait
            logger.warning("Live portrait could not resolve session %s", session_id, exc_info=True)
            runtime = None
        if runtime is None:
            await _unavailable(websocket, "session_unavailable", "The call's session could not be read")
            return
        pack = runtime.avatar_pack
        if pack is None or pack.renderer != "portrait":
            await _unavailable(websocket, "not_a_portrait", "This character's avatar is not a portrait")
            return
        from app.runtime.tenant_context import current_tenant

        try:
            image = await asyncio.to_thread(default_character_avatar_service().portrait_image, pack,
                                            max_bytes=MAX_PORTRAIT_BYTES)
            latent_key = await _prepare_when_loaded(websocket, base_url, current_tenant().workspace_id, image,
                                                    lambda: calls.open(call))
            if latent_key is None:  # the browser left, or the call ended, while the model loaded
                with contextlib.suppress(Exception):
                    await websocket.close(code=1000, reason="call_ended")
                return
            quality = QualityController(starting_level(websocket.client.host if websocket.client else None))

            async def relay(message: bytes) -> None:
                if _is_speech_frame(message):
                    quality.relayed()
                await websocket.send_bytes(message)

            link = await PortraitLink.open(base_url, call_key=call.call_key, principal=principal, session=session_id,
                                           latent_key=latent_key,
                                           emotion=portrait_emotion_label(pack, runtime.speech_style.emotion),
                                           on_frame=relay,
                                           level=quality.level)
        except PortraitUnavailable as exc:
            await _unavailable(websocket, exc.code, str(exc) or "The portrait is not available")
            return
        except Exception:  # noqa: BLE001 - the call goes on without a portrait
            logger.warning("Live portrait could not start for session %s", session_id, exc_info=True)
            await _unavailable(websocket, "portrait_failed", "The portrait could not start")
            return
        if not calls.open(call):
            # The call ended while its portrait loaded or opened: the TTS route has already closed whatever was
            # attached, so this link would hold the service's stream slot with nothing to close it.
            await link.close()
            with contextlib.suppress(Exception):
                await websocket.close(code=1000, reason="call_ended")
            return
        call.attach(link)  # no await since the check: the TTS route cannot end the call in between
        try:
            await websocket.send_json({"type": "ready", "fallback_renderer": pack.fallback_renderer,
                                       "level": quality.level})
            while True:
                if link.closed:
                    await _unavailable(websocket, "portrait_lost", "The portrait stopped")
                    return
                try:
                    raw = await asyncio.wait_for(websocket.receive_text(), LINK_CHECK_SECONDS)
                except asyncio.TimeoutError:
                    continue
                message = json.loads(raw)
                if isinstance(message, dict) and message.get("type") == "frame_ack":
                    call.play_position(str(message["segment_id"])[:160], _count(message["offset"]),
                                       _finite(message.get("round_trip_seconds")))
                    level = quality.observe(time.monotonic(), received=_count(message.get("received")),
                                            late=_count(message.get("late")),
                                            decode_ms=_finite(message.get("decode_ms")))
                    if level is not None:
                        link.send({"type": "quality", "level": level})
                        await websocket.send_json({"type": "quality", "level": level})
        except WebSocketDisconnect:
            pass
        except (ValueError, KeyError, TypeError):
            with contextlib.suppress(Exception):
                await websocket.close(code=1003, reason="bad_message")
        finally:
            call.detach(link)
            await link.close()


__all__ = ["AVATAR_WEBSOCKET_PATH", "register_live_call_avatar_websocket"]
