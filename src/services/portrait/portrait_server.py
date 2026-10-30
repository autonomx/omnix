"""Omnix live portrait service (docs/architecture/OMNIX_LIVE_PORTRAIT_ROADMAP.md, Phase 1).

FLOAT turns a call's TTS audio into a talking-head video of a character's portrait. The gateway talks to
this service only; the browser never does. Routes:

- ``GET /health``: the model's state (``missing``, ``short``, ``warming``, ``ready``, ``failed``), streams in
  use, free VRAM and host commit.
- ``POST /portrait/prepare``: form fields ``tenant`` and ``image_sha256`` and the image file. Crops and
  encodes the portrait once per (tenant, image digest, FLOAT revision) and returns its ``latent_key``.
- ``DELETE /portrait/cache/{tenant}/{image_sha256}``: forget that encoding (its pack was deleted).
- ``WS /portrait/stream``: one call's stream. The first message is ``open`` (``call_key``, ``principal``,
  ``session``, ``latent_key``, ``emotion``); then ``phrase_start``, PCM (binary, see
  ``app.conversation.portrait_stream_contract``), ``phrase_done``, ``output_end``, ``cancel``,
  ``tts_priority``, ``play_position`` and ``heartbeat``. Frames come back as binary JPEG messages.

Loading takes about a minute (cuDNN builds its plans for each network's one input shape), so the model loads
in the background when the service starts and stays resident until it has been idle for a long while. One
stream per GPU by default: a stream is a lease kept by heartbeats; the same principal and session reopening
(a browser reload) replaces its old stream, and any other call is refused with ``portrait_busy``. Outcomes the
gateway acts on travel as ``{"ok": false, "code", "message"}`` (the middleware replaces error bodies).
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import queue
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect

from app.config.env import env_int
from app.conversation.portrait_stream_contract import PortraitMessageError, pack, unpack
from app.runtime.net import bind_host
from app.security.model_service import ModelServiceMiddleware

logger = logging.getLogger(__name__)

LOAD_VRAM_GB = 2.5
LOAD_COMMIT_BYTES = 6 * 1024**3
MAX_IMAGE_UPLOAD_BYTES = 12 * 1024 * 1024
OPEN_TIMEOUT_SECONDS = 5.0
OUTBOX_FRAMES = 256


class Unavailable(RuntimeError):
    """The model cannot serve now; ``code`` says why."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def portrait_key(tenant: str, image_sha256: str) -> str:
    """The cache key: the tenant, the image's digest and the FLOAT code revision it was encoded with."""
    from app.models.catalog import load

    revision = load().model("float-code").revision
    return hashlib.sha256(f"{tenant}\x00{image_sha256}\x00{revision}".encode()).hexdigest()


def _default_load() -> Any:
    from services.portrait.float_runtime import FloatRuntime, required_folders

    return FloatRuntime(required_folders())


def _default_resources() -> tuple[bool, str]:
    """Whether a load fits now (free VRAM and host commit), and why not."""
    from app.providers.host_memory import available_commit_bytes
    from services.helper_models import free_vram_gb

    free = free_vram_gb()
    if free is not None and free < LOAD_VRAM_GB:
        return False, f"The portrait needs about {LOAD_VRAM_GB} GB of VRAM but {free:.1f} GB is free"
    commit = available_commit_bytes()
    if commit is not None and commit < LOAD_COMMIT_BYTES:
        return False, f"The portrait needs about {LOAD_COMMIT_BYTES // 1024**3} GB of host memory to load"
    return True, ""


def _default_installed() -> tuple[bool, str]:
    from services.portrait.float_runtime import PortraitModelMissing, required_folders

    try:
        required_folders()
    except PortraitModelMissing as exc:
        return False, str(exc)
    return True, ""


class RuntimeHost:
    """The loaded model and its state; loads on a background thread, unloads after a long idle."""

    def __init__(self, load: Callable[[], Any], installed: Callable[[], tuple[bool, str]],
                 resources: Callable[[], tuple[bool, str]]) -> None:
        self._load, self._installed, self._resources = load, installed, resources
        self.runtime: Any = None
        self.status = "unloaded"
        self.message = ""
        self.last_used = time.monotonic()
        self._lock = threading.Lock()

    def ensure_loading(self) -> None:
        with self._lock:
            if self.status in {"warming", "ready"}:
                return
            installed, why = self._installed()
            if not installed:
                self.status, self.message = "missing", why
                return
            fits, why = self._resources()
            if not fits:
                self.status, self.message = "short", why
                return
            self.status, self.message = "warming", "The portrait model is loading"
        threading.Thread(target=self._load_now, name="omnix-portrait-load", daemon=True).start()

    def _load_now(self) -> None:
        started = time.monotonic()
        try:
            runtime = self._load()
        except Exception as exc:  # noqa: BLE001 - reported in /health; the next request retries
            logger.exception("Portrait model failed to load")
            with self._lock:
                self.status, self.message = "failed", f"The portrait model failed to load ({type(exc).__name__})"
            return
        with self._lock:
            self.runtime, self.status, self.message = runtime, "ready", ""
            self.last_used = time.monotonic()
        logger.info("Portrait model ready in %.1f s", time.monotonic() - started)

    def get(self) -> Any:
        """The ready runtime, or Unavailable (and a load is started when one can be)."""
        with self._lock:
            if self.status == "ready":
                self.last_used = time.monotonic()
                return self.runtime
        self.ensure_loading()
        with self._lock:
            if self.status == "ready":
                return self.runtime
            code = {"missing": "model_missing", "short": "model_busy", "warming": "warming"}.get(self.status,
                                                                                               "model_failed")
            raise Unavailable(code, self.message or "The portrait model is not ready")

    def unload_if_idle(self, idle_seconds: float, active_streams: int) -> bool:
        with self._lock:
            if self.status != "ready" or active_streams or time.monotonic() - self.last_used < idle_seconds:
                return False
            self.runtime, self.status, self.message = None, "unloaded", ""
        with contextlib.suppress(Exception):
            import torch

            torch.cuda.empty_cache()
        return True


@dataclass
class Lease:
    call_key: str
    principal: str
    session: str
    websocket: WebSocket
    last_seen: float = field(default_factory=time.monotonic)


class Admission:
    """Streams in use, as leases kept alive by heartbeats."""

    def __init__(self, max_streams: int, timeout_seconds: float) -> None:
        self.max_streams = max_streams
        self.timeout_seconds = timeout_seconds
        self.leases: dict[str, Lease] = {}
        self._lock = threading.Lock()

    def admit(self, lease: Lease) -> tuple[bool, list[Lease]]:
        """Admit ``lease``; returns whether it was admitted and the leases it replaced or found expired."""
        now = time.monotonic()
        with self._lock:
            evicted = [item for item in self.leases.values()
                       if now - item.last_seen > self.timeout_seconds
                       or (item.principal, item.session) == (lease.principal, lease.session)]
            for item in evicted:
                self.leases.pop(item.call_key, None)
            if len(self.leases) >= self.max_streams:
                return False, evicted
            self.leases[lease.call_key] = lease
            return True, evicted

    def expired(self) -> list[Lease]:
        now = time.monotonic()
        with self._lock:
            gone = [item for item in self.leases.values() if now - item.last_seen > self.timeout_seconds]
            for item in gone:
                self.leases.pop(item.call_key, None)
            return gone

    def release(self, lease: Lease) -> None:
        with self._lock:
            if self.leases.get(lease.call_key) is lease:
                del self.leases[lease.call_key]

    @property
    def active(self) -> int:
        with self._lock:
            return len(self.leases)


class StreamWorker:
    """Runs one call's PortraitStream on its own thread; messages in through ``inbox``, frames out by ``emit``."""

    def __init__(self, stream: Any) -> None:
        self.stream = stream
        self.inbox: queue.Queue[tuple[str, dict[str, Any], Any] | None] = queue.Queue()
        self.thread = threading.Thread(target=self._run, name="omnix-portrait-stream", daemon=True)
        self.failed: BaseException | None = None

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.inbox.put(None)

    def _apply(self, kind: str, message: dict[str, Any], payload: Any) -> None:
        stream = self.stream
        if kind == "pcm":
            stream.pcm(str(message["segment_id"]), int(message["offset"]), payload)
        elif kind == "phrase_start":
            stream.phrase_start(str(message["output_id"]), int(message["epoch"]), str(message["segment_id"]),
                                int(message["sample_rate"]))
        elif kind == "phrase_done":
            stream.phrase_done(str(message["segment_id"]))
        elif kind == "output_end":
            stream.output_end(str(message["output_id"]), int(message["epoch"]))
        elif kind == "play_position":
            stream.play_position(str(message["segment_id"]), int(message["offset"]),
                                 float(message.get("round_trip_seconds") or 0.0))

    def _run(self) -> None:
        try:
            while True:
                try:
                    item = self.inbox.get(timeout=0.02)
                except queue.Empty:
                    item = ("", {}, None)  # no message: still check deadlines
                if item is None:
                    return
                if item[0]:
                    self._apply(*item)
                    while True:  # take everything already queued before working
                        try:
                            queued = self.inbox.get_nowait()
                        except queue.Empty:
                            break
                        if queued is None:
                            return
                        self._apply(*queued)
                self.stream.pump()
        except BaseException as exc:  # noqa: BLE001 - surfaced to the websocket handler
            logger.exception("Portrait stream failed")
            self.failed = exc


def create_app(*, load: Callable[[], Any] = _default_load,
               installed: Callable[[], tuple[bool, str]] = _default_installed,
               resources: Callable[[], tuple[bool, str]] = _default_resources,
               max_streams: int | None = None, lease_seconds: float = 6.0,
               idle_unload_seconds: float | None = None, preload: bool = True) -> FastAPI:
    """The service app; tests pass their own model loader and checks."""
    from services.portrait.portrait_image import PortraitImageError

    host = RuntimeHost(load, installed, resources)
    admission = Admission(max_streams or env_int("OMNIX_PORTRAIT_MAX_STREAMS", 1, minimum=1, maximum=4),
                          lease_seconds)
    idle_seconds = idle_unload_seconds if idle_unload_seconds is not None else float(
        env_int("OMNIX_PORTRAIT_IDLE_UNLOAD_SECONDS", 1800, minimum=60, maximum=86_400))
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="omnix-portrait-prepare")
    app = FastAPI(title="Omnix live portrait", version="1.0.0")
    app.add_middleware(ModelServiceMiddleware)
    app.state.host, app.state.admission = host, admission

    @app.get("/health")
    def health() -> dict[str, Any]:
        from app.providers.host_memory import available_commit_bytes
        from services.helper_models import free_vram_gb

        free, commit = free_vram_gb(), available_commit_bytes()
        return {"ok": True, "status": host.status, "message": host.message,
                "streams": {"active": admission.active, "max": admission.max_streams},
                "gpu": {"vram_free_bytes": int(free * 1024**3)} if free is not None else {},
                "host": {"commit_free_bytes": commit} if commit is not None else {}}

    @app.post("/portrait/prepare")
    async def prepare(tenant: str = Form(..., min_length=1, max_length=200),  # noqa: B008
                      image_sha256: str = Form(..., min_length=64, max_length=64),  # noqa: B008
                      file: UploadFile = File(...)) -> dict[str, Any]:  # noqa: B008
        payload = await file.read(MAX_IMAGE_UPLOAD_BYTES + 1)
        if not payload or len(payload) > MAX_IMAGE_UPLOAD_BYTES:
            raise HTTPException(status_code=413 if payload else 400, detail="invalid_image")
        if hashlib.sha256(payload).hexdigest() != image_sha256.lower():
            raise HTTPException(status_code=400, detail="digest_mismatch")
        try:
            runtime = host.get()
        except Unavailable as exc:
            return {"ok": False, "code": exc.code, "message": str(exc)}
        key = portrait_key(tenant, image_sha256.lower())
        try:
            await asyncio.get_running_loop().run_in_executor(executor, runtime.prepare, key, payload)
        except PortraitImageError as exc:
            return {"ok": False, "code": exc.code, "message": str(exc)}
        return {"ok": True, "latent_key": key}

    @app.delete("/portrait/cache/{tenant}/{image_sha256}")
    def forget(tenant: str, image_sha256: str) -> dict[str, Any]:
        if host.status == "ready":
            host.runtime.forget(portrait_key(tenant, image_sha256.lower()))
        return {"ok": True}

    @app.websocket("/portrait/stream")
    async def stream(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            opened = json.loads(await asyncio.wait_for(websocket.receive_text(), OPEN_TIMEOUT_SECONDS))
            call_key, principal = str(opened["call_key"]), str(opened["principal"])
            session_id, latent_key = str(opened["session"]), str(opened["latent_key"])
            if opened.get("type") != "open" or not call_key or not latent_key:
                raise ValueError("not an open message")
        except (asyncio.TimeoutError, ValueError, KeyError, TypeError):
            await websocket.close(code=1008, reason="open_expected")
            return
        try:
            runtime = host.get()
        except Unavailable as exc:
            await _refuse(websocket, exc.code, str(exc))
            return
        portrait = runtime.portrait(latent_key)
        if portrait is None:
            await _refuse(websocket, "portrait_not_prepared", "Prepare the portrait before streaming")
            return
        lease = Lease(call_key, principal, session_id, websocket)
        admitted, evicted = admission.admit(lease)
        for old in evicted:
            with contextlib.suppress(Exception):
                await old.websocket.close(code=4000, reason="replaced")
        if not admitted:
            await _refuse(websocket, "portrait_busy", "Another call is using the portrait")
            return

        from services.portrait.scheduler import PortraitStream

        loop = asyncio.get_running_loop()
        outbox: asyncio.Queue[bytes] = asyncio.Queue(maxsize=OUTBOX_FRAMES)
        dropped = 0

        def queue_frame(message: bytes) -> None:
            nonlocal dropped
            try:
                outbox.put_nowait(message)
            except asyncio.QueueFull:
                dropped += 1  # a frame this late would be dropped by the browser anyway

        def emit(frame: Any) -> None:
            header = {"output_id": frame.output_id, "epoch": frame.epoch, "segment_id": frame.segment_id,
                      "offset": frame.offset}
            loop.call_soon_threadsafe(queue_frame, pack(header, frame.jpeg))

        portrait_stream = PortraitStream(runtime.session(portrait, str(opened.get("emotion") or "neutral")), emit,
                                         resample=runtime.resample)
        worker = StreamWorker(portrait_stream)
        worker.start()

        async def send_frames() -> None:
            while True:
                await websocket.send_bytes(await outbox.get())

        sender = asyncio.create_task(send_frames())
        await websocket.send_json({"type": "ready"})
        try:
            while worker.failed is None:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
                host.last_used = lease.last_seen = time.monotonic()
                if message.get("bytes") is not None:
                    try:
                        header, payload = unpack(message["bytes"])
                        worker.inbox.put(("pcm", header, np.frombuffer(payload, dtype="<i2")))
                    except (PortraitMessageError, ValueError):
                        await websocket.send_json({"type": "error", "code": "bad_audio"})
                    continue
                control = json.loads(message.get("text") or "{}")
                kind = str(control.get("type") or "")
                if kind == "cancel":  # takes effect between micro-batches, not after the queue drains
                    portrait_stream.cancel(str(control["output_id"]), int(control["epoch"]))
                elif kind == "tts_priority":
                    (portrait_stream.priority.set if control.get("on") else portrait_stream.priority.clear)()
                elif kind in {"phrase_start", "phrase_done", "output_end", "play_position"}:
                    worker.inbox.put((kind, control, None))
        except WebSocketDisconnect:
            pass
        except (ValueError, KeyError, TypeError):
            with contextlib.suppress(Exception):
                await websocket.close(code=1003, reason="bad_message")
        finally:
            portrait_stream.priority.clear()
            worker.stop()
            sender.cancel()
            admission.release(lease)
            if dropped:
                logger.info("Portrait stream %s dropped %d late frames", call_key, dropped)

    async def _refuse(websocket: WebSocket, code: str, message: str) -> None:
        await websocket.send_json({"type": "refused", "code": code, "message": message})
        await websocket.close(code=4001, reason=code)

    @app.on_event("startup")
    async def start() -> None:
        if preload:
            host.ensure_loading()

        async def housekeeping() -> None:
            while True:
                await asyncio.sleep(1.0)
                for lease in admission.expired():
                    with contextlib.suppress(Exception):
                        await lease.websocket.close(code=4002, reason="lease_expired")
                if host.unload_if_idle(idle_seconds, admission.active):
                    logger.info("Unloaded the idle portrait model")

        app.state.housekeeping = asyncio.create_task(housekeeping())

    return app


app = create_app()


def main() -> None:
    from app.observability.logging import configure_logging

    configure_logging()
    host = bind_host()
    port = env_int("OMNIX_PORTRAIT_PORT", 5501, minimum=1, maximum=65535)
    print(f"[PORTRAIT] Starting the live portrait service on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()


__all__ = ["Admission", "Lease", "RuntimeHost", "StreamWorker", "Unavailable", "app", "create_app", "main"]
