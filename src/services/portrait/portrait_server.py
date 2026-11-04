"""Omnix live portrait service (docs/architecture/OMNIX_LIVE_PORTRAIT_ROADMAP.md, Phase 1).

FLOAT turns a call's TTS audio into a talking-head video of a character's portrait. The gateway talks to
this service only; the browser never does. Routes:

- ``GET /health``: the model's state (``missing``, ``short``, ``warming``, ``ready``, ``failed``), streams in
  use, free VRAM and host commit.
- ``POST /portrait/prepare``: form fields ``tenant`` and ``image_sha256`` and the image file. Crops and
  encodes the portrait once per (tenant, image digest, FLOAT revision) and returns its ``latent_key``.
- ``DELETE /portrait/cache/{tenant}/{image_sha256}``: forget that encoding and its idle loop (no pack shows it).
- ``POST /portrait/preview``: form fields ``latent_key``, ``emotion``, ``sample_rate`` and up to 8 s of 16-bit PCM:
  the frames for that audio, rendered as a call's would be (base64 JPEGs, 25 a second), for the setup preview.
  Refused with ``portrait_busy`` while a call streams.
- ``WS /portrait/stream``: one call's stream. The first message is ``open`` (``call_key``, ``principal``,
  ``session``, ``latent_key``, ``emotion``, ``level``); then ``phrase_start``, PCM (binary, see
  ``app.conversation.portrait_stream_contract``), ``phrase_done``, ``output_end``, ``cancel``,
  ``tts_priority``, ``play_position``, ``quality``, the speculation messages (``spec_start``, ``spec_drop``,
  ``spec_bind``, ``spec_prefix_end``, see ``services.portrait.scheduler``) and ``heartbeat``. Frames come back as
  binary JPEG messages: after ``ready``, the portrait's idle loop at the opening level, then the call's speech.

Loading takes about a minute (cuDNN builds its plans for each network's one input shape). The model loads on
demand, when a call to a character with a portrait (or the avatar setup's preview) first asks for it; until
then the service holds no model and no CUDA context (``OMNIX_PORTRAIT_PRELOAD=1`` loads it at start instead).
After ten minutes without a call it unloads and the process exits with ``IDLE_EXIT_CODE``, which its launcher
answers by starting it again, light: only the process's end releases its CUDA context. One
stream per GPU by default: a stream is a lease kept by heartbeats; the same principal and session reopening
(a browser reload) replaces its old stream, and any other call is refused with ``portrait_busy``. Outcomes the
gateway acts on travel as ``{"ok": false, "code", "message"}`` (the middleware replaces error bodies).
"""
from __future__ import annotations

import asyncio
import collections
import contextlib
import hashlib
import json
import logging
import queue
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect

from app.config.env import env_bool, env_int
from app.conversation.portrait_stream_contract import QUALITY_LEVELS, PortraitMessageError, pack, unpack
from app.runtime.net import bind_host
from app.runtime.process_control import IDLE_EXIT_CODE
from app.security.model_service import ModelServiceMiddleware

logger = logging.getLogger(__name__)

LOAD_VRAM_GB = 4.0  # the runtime's allocator cap (float_runtime.VRAM_CAP_MB); the load peaks at 3.5 GB
LOAD_COMMIT_BYTES = 8 * 1024**3  # the load's process commit peaks at 6.4-6.7 GB
MAX_IMAGE_UPLOAD_BYTES = 12 * 1024 * 1024
OPEN_TIMEOUT_SECONDS = 5.0
OUTBOX_FRAMES = 256
MAX_PREVIEW_SECONDS = 8
# Control messages a stream applies in order on the GPU thread (``cancel`` and ``tts_priority`` act at once).
STREAM_MESSAGES = frozenset({"phrase_start", "phrase_done", "output_end", "play_position", "quality", "spec_start",
                             "spec_drop", "spec_bind", "spec_prefix_end"})
# The fields each control message needs (checked as it arrives, so a malformed one never reaches the GPU thread);
# counts are integers of at least 0, and a sample rate is a real one.
MESSAGE_FIELDS: dict[str, tuple[str, ...]] = {
    "phrase_start": ("output_id", "epoch", "segment_id", "sample_rate"), "phrase_done": ("segment_id",),
    "output_end": ("output_id", "epoch"), "play_position": ("segment_id", "offset"), "quality": (),
    "spec_start": ("generation_id", "sample_rate"), "spec_drop": ("generation_id",),
    "spec_bind": ("generation_id", "output_id", "epoch", "segment_id"),
    "spec_prefix_end": ("generation_id", "segment_id", "samples"), "cancel": ("output_id", "epoch")}
COUNT_FIELDS = frozenset({"epoch", "offset", "samples", "trim"})
MIN_SAMPLE_RATE, MAX_SAMPLE_RATE = 8_000, 192_000
# How often a stream's handler looks at its worker when no message comes (a failed stream is closed at once).
WORKER_CHECK_SECONDS = 0.5


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


def free_vram_gb() -> float | None:
    """Free memory on the first visible GPU from the driver's NVML (None without one).

    Never through CUDA: asking CUDA creates the context (about 2.5 GB of commit) that the light, model-free process
    is meant not to hold, and a check that found too little would keep it for good.
    """
    import ctypes
    import os

    class Memory(ctypes.Structure):
        _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong), ("used", ctypes.c_ulonglong)]

    try:
        nvml = ctypes.CDLL("nvml.dll" if sys.platform == "win32" else "libnvidia-ml.so.1")
    except OSError:
        return None
    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "").split(",")[0].strip()
    if nvml.nvmlInit_v2() != 0:
        return None
    try:
        handle, memory = ctypes.c_void_p(), Memory()
        if nvml.nvmlDeviceGetHandleByIndex_v2(ctypes.c_uint(int(visible) if visible.isdigit() else 0),
                                             ctypes.byref(handle)) != 0:
            return None
        if nvml.nvmlDeviceGetMemoryInfo(handle, ctypes.byref(memory)) != 0:
            return None
        return memory.free / 1024**3
    finally:
        nvml.nvmlShutdown()


def _cuda_initialized() -> bool:
    torch = sys.modules.get("torch")
    return torch is not None and torch.cuda.is_initialized()


def _default_resources() -> tuple[bool, str]:
    """Whether a load fits now (free VRAM and host commit), and why not."""
    from app.models.host_memory import available_commit_bytes

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
    """The loaded model and its state, and the one thread that does all of its GPU work.

    Loading, the warm-up, every ``prepare`` and every stream's passes run on the same long-lived thread:
    cuDNN's per-shape setup (about a minute in all) is kept per thread, so work on any other thread would
    pay it again. Streams are stepped in turn between tasks. Unloads after a long idle.
    """

    def __init__(self, load: Callable[[], Any], installed: Callable[[], tuple[bool, str]],
                 resources: Callable[[], tuple[bool, str]]) -> None:
        self._load, self._installed, self._resources = load, installed, resources
        self.runtime: Any = None
        self.status = "unloaded"
        self.message = ""
        self.last_used = time.monotonic()
        self._lock = threading.Lock()
        self._tasks: queue.Queue[tuple[Callable[..., Any], tuple[Any, ...], Future[Any]]] = queue.Queue()
        self._workers: list[StreamWorker] = []
        self._thread: threading.Thread | None = None

    def submit(self, function: Callable[..., Any], *args: Any) -> Future[Any]:
        """Run ``function`` on the GPU thread."""
        future: Future[Any] = Future()
        self._tasks.put((function, args, future))
        self._start_thread()
        return future

    def attach(self, worker: StreamWorker) -> None:
        with self._lock:
            self._workers.append(worker)
        self._start_thread()

    def detach(self, worker: StreamWorker) -> None:
        with self._lock:
            if worker in self._workers:
                self._workers.remove(worker)

    def _start_thread(self) -> None:
        with self._lock:
            if self._thread is None:
                self._thread = threading.Thread(target=self._gpu_loop, name="omnix-portrait-gpu", daemon=True)
                self._thread.start()

    def _gpu_loop(self) -> None:
        while True:
            with self._lock:
                streaming = bool(self._workers)
            try:
                function, args, future = self._tasks.get(timeout=0.005 if streaming else 0.05)
            except queue.Empty:
                pass
            else:
                if future.set_running_or_notify_cancel():
                    try:
                        future.set_result(function(*args))
                    except BaseException as exc:  # noqa: BLE001 - handed to whoever submitted it
                        future.set_exception(exc)
            with self._lock:
                workers = list(self._workers)
            for worker in workers:
                worker.step()

    def ensure_loading(self) -> None:
        with self._lock:
            if self.status in {"warming", "ready", "exiting"}:
                return
            try:
                installed, why = self._installed()
                fits, short = self._resources() if installed else (True, "")
            except Exception as exc:  # noqa: BLE001 - a broken check is reported, never fatal to the service
                logger.exception("Portrait load check failed")
                self.status, self.message = "failed", f"The portrait load check failed ({type(exc).__name__})"
                return
            if not installed:
                self.status, self.message = "missing", why
                return
            if not fits:
                self.status, self.message = "short", short
                return
            self.status, self.message = "warming", "The portrait model is loading"
        self.submit(self._load_now)

    def _load_now(self) -> None:
        started = time.monotonic()
        try:
            runtime = self._load()
        except Exception as exc:  # noqa: BLE001 - reported in /health; the next request retries
            logger.exception("Portrait model failed to load")
            with self._lock:
                self.status, self.message = "failed", f"The portrait model failed to load ({type(exc).__name__})"
                self.last_used = time.monotonic()  # an idle while from now, its CUDA context goes with the process
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
            code = {"missing": "model_missing", "short": "model_busy", "warming": "warming",
                    "exiting": "service_unreachable"}.get(self.status, "model_failed")
            raise Unavailable(code, self.message or "The portrait model is not ready")

    def ready_runtime(self) -> Any:
        """The loaded runtime, or None (read under the lock: an unload may be under way)."""
        with self._lock:
            return self.runtime if self.status == "ready" else None

    def unload_if_idle(self, idle_seconds: float, active_streams: int, *, exit_after: bool = False) -> bool:
        """Unload a model idle for ``idle_seconds`` with no stream open.

        With ``exit_after`` the process exits next: the status becomes ``exiting``, so nothing loads in the
        meantime, and a failed load that left a CUDA context behind is given up the same way.
        """
        with self._lock:
            if active_streams or time.monotonic() - self.last_used < idle_seconds:
                return False
            if self.status != "ready" and not (exit_after and self.status == "failed" and _cuda_initialized()):
                return False
            self.runtime, self.message = None, "The portrait service is restarting" if exit_after else ""
            self.status = "exiting" if exit_after else "unloaded"
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
    """One call's PortraitStream, stepped by the GPU thread; messages in through ``inbox``, frames out by ``emit``."""

    def __init__(self, stream: Any) -> None:
        self.stream = stream
        self.inbox: queue.Queue[tuple[str, dict[str, Any], Any]] = queue.Queue()
        self.failed: BaseException | None = None

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
                                 float(message.get("round_trip_seconds") or 0.0), message.get("received_at"))
        elif kind == "quality":
            stream.session.level = quality_level(message.get("level"))
            for _output, session in stream.speculative.values():
                session.level = stream.session.level
        elif kind == "spec_start":
            stream.spec_start(str(message["generation_id"]), int(message["sample_rate"]))
        elif kind == "spec_drop":
            stream.spec_drop(str(message["generation_id"]))
        elif kind == "spec_bind":
            stream.spec_bind(str(message["generation_id"]), str(message["output_id"]), int(message["epoch"]),
                             str(message["segment_id"]), int(message.get("trim") or 0))
        elif kind == "spec_prefix_end":
            stream.spec_prefix_end(str(message["generation_id"]), str(message["segment_id"]), int(message["samples"]))

    def step(self) -> None:
        """Take every queued message, then run the passes they allow (and any deadline that came)."""
        if self.failed is not None:
            return
        try:
            while True:
                try:
                    self._apply(*self.inbox.get_nowait())
                except queue.Empty:
                    break
            self.stream.pump()
        except Exception as exc:  # noqa: BLE001 - surfaced to the websocket handler
            logger.exception("Portrait stream failed")
            self.failed = exc


class PreviewAborted(RuntimeError):
    """A call started while a preview rendered: the call has the GPU."""


class _GivesWay:
    """A preview's motion session that stops between passes and decodes once ``abort`` says a call started."""

    def __init__(self, session: Any, abort: Callable[[], bool]) -> None:
        self._session, self._abort = session, abort

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)

    def run_pass(self, *args: Any) -> None:
        if self._abort():
            raise PreviewAborted
        self._session.run_pass(*args)

    def decode(self, *args: Any) -> Any:
        if self._abort():
            raise PreviewAborted
        return self._session.decode(*args)


def render_preview(runtime: Any, portrait: Any, emotion: str, pcm: np.ndarray, sample_rate: int,
                   abort: Callable[[], bool] = lambda: False) -> list[bytes]:
    """Every frame for a short clip, through the same scheduler a call uses (so the GPU sees the same shapes).

    Only the clip's own frames: not the transition back to the idle loop a call's reply ends with. Raises
    PreviewAborted, between passes, once ``abort`` is true.
    """
    from services.portrait.scheduler import TRANSITION_OUTPUT_ID, PortraitStream, StreamSettings

    frames: list[bytes] = []
    stream = PortraitStream(_GivesWay(runtime.session(portrait, emotion), abort),
                            lambda frame: frames.append(frame.jpeg) if frame.output_id != TRANSITION_OUTPUT_ID else None,
                            resample=runtime.resample,
                            settings=StreamSettings(render_ahead_seconds=None))  # the whole clip, nothing plays it
    stream.phrase_start("preview", 0, "preview", sample_rate)
    stream.pcm("preview", 0, pcm)
    stream.phrase_done("preview")
    stream.output_end("preview", 0)
    stream.pump()
    return frames


def check_message(kind: str, message: dict[str, Any]) -> None:
    """Raise ValueError (or KeyError) for a control message missing a field or carrying a bad one."""
    for name in MESSAGE_FIELDS.get(kind, ()):
        if message[name] is None:
            raise ValueError(f"{kind} needs {name}")
    for name in COUNT_FIELDS & message.keys():
        if message[name] is not None and int(message[name]) < 0:
            raise ValueError(f"{name} is negative")
    if "sample_rate" in message and not MIN_SAMPLE_RATE <= int(message["sample_rate"]) <= MAX_SAMPLE_RATE:
        raise ValueError("not a sample rate")


def quality_level(value: Any) -> int:
    """A quality level from a message, clamped to the known levels (0, the best, when absent)."""
    try:
        return min(max(int(value or 0), 0), len(QUALITY_LEVELS) - 1)
    except (TypeError, ValueError):
        return 0


def create_app(*, load: Callable[[], Any] = _default_load,
               installed: Callable[[], tuple[bool, str]] = _default_installed,
               resources: Callable[[], tuple[bool, str]] = _default_resources,
               max_streams: int | None = None, lease_seconds: float = 6.0,
               idle_unload_seconds: float | None = None, preload: bool | None = None) -> FastAPI:
    """The service app; tests pass their own model loader and checks.

    ``app.state.request_exit`` (set by ``main``) is called with ``IDLE_EXIT_CODE`` once the idle model unloads.
    """
    from services.portrait.portrait_image import PortraitImageError

    host = RuntimeHost(load, installed, resources)
    admission = Admission(max_streams or env_int("OMNIX_PORTRAIT_MAX_STREAMS", 1, minimum=1, maximum=4),
                          lease_seconds)
    idle_seconds = idle_unload_seconds if idle_unload_seconds is not None else float(
        env_int("OMNIX_PORTRAIT_IDLE_UNLOAD_SECONDS", 600, minimum=60, maximum=86_400))
    if preload is None:
        preload = env_bool("OMNIX_PORTRAIT_PRELOAD", False)
    app = FastAPI(title="Omnix live portrait", version="1.0.0")
    app.add_middleware(ModelServiceMiddleware)
    app.state.host, app.state.admission = host, admission
    app.state.request_exit = None

    @app.get("/health")
    def health() -> dict[str, Any]:
        from app.models.host_memory import available_commit_bytes

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
            portrait = await asyncio.wrap_future(host.submit(runtime.prepare, key, payload))
        except PortraitImageError as exc:
            return {"ok": False, "code": exc.code, "message": str(exc)}
        # A prepared portrait is ready for a call. Rendered at the call's start instead, its idle loop would hold the
        # GPU thread, and with it the first reply's frames, for seconds. Never in the way of a call in progress.
        if not admission.active:
            started = time.monotonic()
            try:
                await asyncio.wrap_future(host.submit(runtime.idle_frames, portrait, 0))
                await asyncio.wrap_future(host.submit(runtime.blink_frames, portrait, 0))
            except Exception:  # noqa: BLE001 - the portrait is prepared; a call renders its idle loop itself
                logger.warning("Portrait idle loop could not be rendered ahead of the call", exc_info=True)
            else:
                if (seconds := time.monotonic() - started) >= 0.05:
                    logger.info("Portrait idle loop rendered in %.1f s", seconds)
        return {"ok": True, "latent_key": key}

    @app.post("/portrait/preview")
    async def preview(latent_key: str = Form(..., min_length=1, max_length=200),  # noqa: B008
                      emotion: str = Form("neutral", max_length=40),  # noqa: B008
                      sample_rate: int = Form(..., ge=8_000, le=48_000),  # noqa: B008
                      file: UploadFile = File(...)) -> dict[str, Any]:  # noqa: B008
        import base64

        payload = await file.read(MAX_PREVIEW_SECONDS * 48_000 * 2 + 1)
        if not payload or len(payload) > MAX_PREVIEW_SECONDS * sample_rate * 2 or len(payload) % 2:
            raise HTTPException(status_code=413 if payload else 400, detail="invalid_audio")
        try:
            runtime = host.get()
        except Unavailable as exc:
            return {"ok": False, "code": exc.code, "message": str(exc)}
        busy = {"ok": False, "code": "portrait_busy", "message": "A call is using the portrait"}
        if admission.active >= admission.max_streams:
            return busy
        portrait = runtime.portrait(latent_key)
        if portrait is None:
            return {"ok": False, "code": "portrait_not_prepared", "message": "Prepare the portrait first"}
        pcm = np.frombuffer(payload, dtype="<i2")
        try:
            frames = await asyncio.wrap_future(host.submit(render_preview, runtime, portrait, emotion, pcm, sample_rate,
                                                           lambda: admission.active > 0))
        except PreviewAborted:  # a call started meanwhile: it gets the GPU, the preview gives way
            return busy
        return {"ok": True, "fps": 25, "frames": [base64.b64encode(frame).decode("ascii") for frame in frames]}

    @app.delete("/portrait/cache/{tenant}/{image_sha256}")
    def forget(tenant: str, image_sha256: str) -> dict[str, Any]:
        runtime = host.ready_runtime()
        if runtime is not None:
            runtime.forget(portrait_key(tenant, image_sha256.lower()))
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

        portrait_stream: Any = None
        worker: StreamWorker | None = None
        tasks: list[asyncio.Task[None]] = []
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
            if frame.count is not None:  # a sequence played by time (the transition back to the idle loop)
                header.update(count=frame.count, frame_ms=frame.frame_ms)
            loop.call_soon_threadsafe(queue_frame, pack(header, frame.jpeg))

        idle_box: collections.deque[bytes] = collections.deque()
        # Remote calls get the idle loop at its own frame rate, so a reply's first frames never queue behind
        # seconds of it in the socket; a loopback call (level 0) gets it at once.
        idle_pace = {"gap": 0.0, "next": 0.0}

        async def send_frames() -> None:
            # Speech first; the idle loop goes out only while no speech frame is waiting.
            while True:
                if outbox.empty() and idle_box:
                    wait = idle_pace["next"] - loop.time()
                    if wait <= 0:
                        await websocket.send_bytes(idle_box.popleft())
                        idle_pace["next"] = loop.time() + idle_pace["gap"]
                        continue
                    try:
                        message = await asyncio.wait_for(outbox.get(), wait)
                    except asyncio.TimeoutError:
                        continue
                else:
                    message = await outbox.get()
                if message:  # an empty message only wakes this loop for the idle loop
                    await websocket.send_bytes(message)

        async def send_idle_loop() -> None:
            from services.portrait.idle_loop import BLINK_OUTPUT_ID, IDLE_OUTPUT_ID, IDLE_SEGMENT_ID, idle_frame_step

            level = session.level
            try:
                frames = await asyncio.wrap_future(host.submit(runtime.idle_frames, portrait, level))
                blink = await asyncio.wrap_future(host.submit(runtime.blink_frames, portrait, level))
            except Exception:  # noqa: BLE001 - the call goes on; the browser holds the last frame instead
                logger.warning("Portrait idle loop failed for %s", call_key, exc_info=True)
                return
            frame_ms = 40 * idle_frame_step(level)
            idle_pace["gap"] = frame_ms / 1000 if level > 0 else 0.0
            for index, jpeg in enumerate(frames):
                idle_box.append(pack({"output_id": IDLE_OUTPUT_ID, "epoch": 0, "segment_id": IDLE_SEGMENT_ID,
                                      "offset": index, "count": len(frames), "frame_ms": frame_ms}, jpeg))
            for index, jpeg in enumerate(blink):  # after the loop: each loop frame with its eyes shut
                idle_box.append(pack({"output_id": BLINK_OUTPUT_ID, "epoch": 0, "segment_id": BLINK_OUTPUT_ID,
                                      "offset": index, "count": len(blink), "frame_ms": frame_ms}, jpeg))
            queue_frame(b"")

        # Everything after admission is undone below, however the stream ends: a gateway that goes away before
        # ``ready``, a session that fails to make, a malformed message, a worker that fails on the GPU thread.
        try:
            # The session's tensors are made on the GPU thread, like all of the model's work.
            session = await asyncio.wrap_future(host.submit(runtime.session, portrait,
                                                            str(opened.get("emotion") or "neutral")))
            session.level = quality_level(opened.get("level"))
            portrait_stream = PortraitStream(session, emit, resample=runtime.resample)
            worker = StreamWorker(portrait_stream)
            host.attach(worker)
            tasks.append(asyncio.create_task(send_frames()))
            await websocket.send_json({"type": "ready"})
            tasks.append(asyncio.create_task(send_idle_loop()))
            while True:
                if worker.failed is not None:
                    with contextlib.suppress(Exception):
                        await websocket.close(code=1011, reason="stream_failed")
                    break
                try:
                    message = await asyncio.wait_for(websocket.receive(), WORKER_CHECK_SECONDS)
                except asyncio.TimeoutError:
                    continue
                if message["type"] == "websocket.disconnect":
                    break
                host.last_used = lease.last_seen = time.monotonic()
                if message.get("bytes") is not None:
                    try:
                        header, payload = unpack(message["bytes"])
                        header = {"segment_id": str(header["segment_id"]), "offset": int(header["offset"])}
                        if header["offset"] < 0:
                            raise ValueError("negative offset")
                        worker.inbox.put(("pcm", header, np.frombuffer(payload, dtype="<i2")))
                    except (PortraitMessageError, ValueError, KeyError, TypeError, OverflowError):
                        await websocket.send_json({"type": "error", "code": "bad_audio"})
                    continue
                control = json.loads(message.get("text") or "{}")
                if not isinstance(control, dict):
                    raise ValueError("a control message is an object")
                kind = str(control.get("type") or "")
                if kind == "cancel":  # takes effect between micro-batches, not after the queue drains
                    check_message(kind, control)
                    portrait_stream.cancel(str(control["output_id"]), int(control["epoch"]))
                elif kind == "tts_priority":
                    (portrait_stream.priority.set if control.get("on") else portrait_stream.priority.clear)()
                elif kind in STREAM_MESSAGES:
                    check_message(kind, control)
                    if kind == "play_position":  # its time is when it came, not when the GPU thread gets to it
                        control["received_at"] = time.monotonic()
                    worker.inbox.put((kind, control, None))
        except WebSocketDisconnect:
            pass
        except (ValueError, KeyError, TypeError, OverflowError):
            with contextlib.suppress(Exception):
                await websocket.close(code=1003, reason="bad_message")
        except Exception:  # noqa: BLE001 - a session that failed to make, or a send to a gateway already gone
            logger.warning("Portrait stream %s ended with an error", call_key, exc_info=True)
            with contextlib.suppress(Exception):
                await websocket.close(code=1011, reason="stream_failed")
        finally:
            if portrait_stream is not None:
                portrait_stream.priority.clear()
            if worker is not None:
                host.detach(worker)
            for task in tasks:
                task.cancel()
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
                if preload:
                    continue  # loaded at start to stay loaded: never unloaded, so never reloaded every idle while
                exiting = app.state.request_exit is not None
                if host.unload_if_idle(idle_seconds, admission.active, exit_after=exiting):
                    if not exiting:
                        logger.info("Unloaded the idle portrait model")
                        continue
                    logger.info("Unloaded the idle portrait model; exiting so its launcher starts the service light")
                    app.state.request_exit(IDLE_EXIT_CODE)
                    return

        app.state.housekeeping = asyncio.create_task(housekeeping())

    return app


app = create_app()


def main() -> None:
    from app.observability.logging import configure_logging

    configure_logging()
    host = bind_host()
    port = env_int("OMNIX_PORTRAIT_PORT", 5501, minimum=1, maximum=65535)
    print(f"[PORTRAIT] Starting the live portrait service on http://{host}:{port}")
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port))
    exit_code = 0

    def request_exit(code: int) -> None:
        nonlocal exit_code
        exit_code, server.should_exit = code, True

    app.state.request_exit = request_exit
    server.run()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()


__all__ = ["Admission", "Lease", "PreviewAborted", "RuntimeHost", "StreamWorker", "Unavailable", "app", "check_message",
           "create_app", "free_vram_gb", "main", "quality_level", "render_preview"]
