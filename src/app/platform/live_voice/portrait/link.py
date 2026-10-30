"""A call's link to the portrait service (services/portrait), and its prepare request.

``OMNIX_PORTRAIT_URL`` names the service; without it there is no portrait. The link is one websocket per call:
the TTS route copies its phrases' PCM in through ``send`` and ``send_pcm``, which never wait (a bounded queue;
when it is full the copy is dropped and the link marked degraded, and the voice is never held up), and frames
come back through ``on_frame`` as the service sent them (``app.conversation.portrait_stream_contract``).
A heartbeat keeps the service's lease on the stream.
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.config.env import env_str
from app.conversation.portrait_stream_contract import pack

logger = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 2.0
QUEUE_LIMIT = 512
OPEN_TIMEOUT_SECONDS = 5.0

FrameHandler = Callable[[bytes], Awaitable[None]]


class PortraitUnavailable(Exception):
    """The portrait cannot serve this call; ``code`` says why (the call falls back)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def portrait_url() -> str:
    """The portrait service's base URL, or '' when the portrait is not set up."""
    return (env_str("OMNIX_PORTRAIT_URL", "") or "").strip().rstrip("/")


async def prepare_portrait(base_url: str, tenant: str, image: bytes, *, client: Any = None) -> str:
    """Encode a portrait on the service; returns its latent key."""
    import httpx

    from app.security.service_token import service_headers

    digest = hashlib.sha256(image).hexdigest()
    owned = client is None
    client = client or httpx.AsyncClient(timeout=30.0, follow_redirects=False)
    try:
        response = await client.post(f"{base_url}/portrait/prepare", headers=service_headers(),
                                     data={"tenant": tenant, "image_sha256": digest},
                                     files={"file": ("portrait", image)})
    except httpx.HTTPError as exc:
        raise PortraitUnavailable("service_unreachable", "The portrait service did not answer") from exc
    finally:
        if owned:
            await client.aclose()
    if response.status_code != 200:
        raise PortraitUnavailable("service_error", f"The portrait service refused the image ({response.status_code})")
    body = response.json()
    if not body.get("ok"):
        raise PortraitUnavailable(str(body.get("code") or "service_error"), str(body.get("message") or ""))
    return str(body["latent_key"])


class PortraitLink:
    """One call's stream to the portrait service."""

    def __init__(self, websocket: Any, on_frame: FrameHandler, *, queue_limit: int = QUEUE_LIMIT) -> None:
        self._websocket = websocket
        self._on_frame = on_frame
        self._outbox: asyncio.Queue[str | bytes] = asyncio.Queue(maxsize=queue_limit)
        self._tasks: list[asyncio.Task[None]] = []
        self.dropped = 0
        self.closed = False

    @classmethod
    async def open(cls, base_url: str, *, call_key: str, principal: str, session: str, latent_key: str,
                   emotion: str, on_frame: FrameHandler, connect: Callable[..., Any] | None = None) -> PortraitLink:
        """Connect, send ``open`` and wait for ``ready``; a refusal raises PortraitUnavailable."""
        from app.security.service_token import service_headers

        if connect is None:
            import websockets

            connect = websockets.connect
        url = "ws" + base_url.removeprefix("http") + "/portrait/stream"
        try:
            websocket = await asyncio.wait_for(
                connect(url, additional_headers=service_headers(), max_size=None), OPEN_TIMEOUT_SECONDS)
            await websocket.send(json.dumps({"type": "open", "call_key": call_key, "principal": principal,
                                             "session": session, "latent_key": latent_key, "emotion": emotion}))
            reply = json.loads(await asyncio.wait_for(websocket.recv(), OPEN_TIMEOUT_SECONDS))
        except (OSError, asyncio.TimeoutError, ValueError) as exc:
            raise PortraitUnavailable("service_unreachable", "The portrait stream could not be opened") from exc
        except Exception as exc:  # noqa: BLE001 - the websockets library's own connection errors
            raise PortraitUnavailable("service_unreachable", f"The portrait stream failed ({type(exc).__name__})") from exc
        if reply.get("type") != "ready":
            with contextlib.suppress(Exception):
                await websocket.close()
            raise PortraitUnavailable(str(reply.get("code") or "refused"), str(reply.get("message") or ""))
        link = cls(websocket, on_frame)
        link._tasks = [asyncio.create_task(link._write()), asyncio.create_task(link._read()),
                       asyncio.create_task(link._heartbeat())]
        return link

    @property
    def degraded(self) -> bool:
        return self.dropped > 0

    def send(self, message: dict[str, Any]) -> None:
        self._put(json.dumps(message, separators=(",", ":")))

    def send_pcm(self, segment_id: str, offset: int, pcm: bytes) -> None:
        self._put(pack({"segment_id": segment_id, "offset": offset}, pcm))

    def _put(self, item: str | bytes) -> None:
        if self.closed:
            return
        try:
            self._outbox.put_nowait(item)
        except asyncio.QueueFull:
            self.dropped += 1
            if self.dropped == 1:
                logger.warning("Portrait link queue full; dropping its copy of the audio")

    async def _write(self) -> None:
        try:
            while True:
                await self._websocket.send(await self._outbox.get())
        except Exception:  # noqa: BLE001 - the link ends; the call falls back
            self.closed = True

    async def _read(self) -> None:
        try:
            async for message in self._websocket:
                if isinstance(message, bytes):
                    await self._on_frame(message)
        except Exception:  # noqa: BLE001 - the link ends; the call falls back
            logger.info("Portrait link closed", exc_info=True)
        finally:
            self.closed = True

    async def _heartbeat(self) -> None:
        while not self.closed:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            self.send({"type": "heartbeat"})

    async def close(self) -> None:
        self.closed = True
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        with contextlib.suppress(Exception):
            await self._websocket.close()


__all__ = ["PortraitLink", "PortraitUnavailable", "portrait_url", "prepare_portrait"]
