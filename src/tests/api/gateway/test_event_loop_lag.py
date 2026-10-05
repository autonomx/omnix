"""The gateway event loop stays responsive while stores are slow (WP-7.1).

A slow fake store (200 ms per call) serves job and chat-session reads while a
health-probe loop and a frame loop (the shape of a live-call WebSocket sender)
run on the same event loop. A watchdog thread measures loop lag as the round
trip of ``call_soon_threadsafe``, which does not depend on timer resolution.
The heap built at start-up is frozen first: a full garbage collection over it
pauses every thread for up to ~150 ms, which is not what this test measures.
"""
from __future__ import annotations

import asyncio
import gc
import threading
import time

import httpx
from fastapi import FastAPI

from app.chat.models import ChatSessionListResponse

STORE_DELAY_SECONDS = 0.2
LOAD_SECONDS = 1.2
CONCURRENT_SLOW_REQUESTS = 8
FRAME_INTERVAL_SECONDS = 0.01
_NEVER_SET = threading.Event()


def _blocking_io() -> None:
    """Stands in for a synchronous database or provider call."""
    _NEVER_SET.wait(STORE_DELAY_SECONDS)


class SlowJobStore:
    def get_job(self, job_id):
        _blocking_io()
        return None


class SlowChatStore:
    def list_sessions(self, **kwargs):
        _blocking_io()
        return ChatSessionListResponse(sessions=[])


class LoopLagProbe:
    """Measures how long the loop takes to run a callback posted from a thread."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.samples_ms: list[float] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            ran = threading.Event()
            started = time.perf_counter()
            self.loop.call_soon_threadsafe(ran.set)
            ran.wait(5)
            self.samples_ms.append((time.perf_counter() - started) * 1000)
            self._stop.wait(0.005)

    def __enter__(self) -> LoopLagProbe:
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join(5)


def _p99(values: list[float]) -> float:
    if not values:  # the loop never got to take a sample
        return float("inf")
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * 0.99))]


async def _measure(app: FastAPI, slow_paths: list[str]) -> dict[str, float]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://127.0.0.1",
        headers={"X-Omnix-Client": "test"},
    ) as client:
        # Warm route state and the worker pool outside the measurement.
        assert (await client.get("/health")).status_code == 200
        for path in slow_paths:
            await client.get(path)

        deadline = time.perf_counter() + LOAD_SECONDS
        health_ms: list[float] = []
        frame_gaps_ms: list[float] = []

        async def slow_reads(path: str) -> None:
            while time.perf_counter() < deadline:
                await client.get(path)

        async def health_probes() -> None:
            while time.perf_counter() < deadline:
                started = time.perf_counter()
                assert (await client.get("/health")).status_code == 200
                health_ms.append((time.perf_counter() - started) * 1000)
                await asyncio.sleep(0.02)

        async def frames() -> None:
            previous = time.perf_counter()
            while time.perf_counter() < deadline:
                await asyncio.sleep(FRAME_INTERVAL_SECONDS)
                now = time.perf_counter()
                frame_gaps_ms.append((now - previous) * 1000)
                previous = now

        gc.collect()
        gc.freeze()
        try:
            with LoopLagProbe(asyncio.get_running_loop()) as probe:
                await asyncio.gather(
                    *(slow_reads(slow_paths[i % len(slow_paths)]) for i in range(CONCURRENT_SLOW_REQUESTS)),
                    health_probes(),
                    frames(),
                )
        finally:
            gc.unfreeze()
        return {
            "lag_p99_ms": _p99(probe.samples_ms),
            "health_p99_ms": _p99(health_ms),
            "frame_gap_p99_ms": _p99(frame_gaps_ms),
        }


def test_slow_stores_do_not_stall_the_gateway_event_loop() -> None:
    from app.gateway.main import create_gateway_app

    gateway = create_gateway_app(
        job_store_factory=SlowJobStore,
        chat_store_factory=SlowChatStore,
    )

    result = asyncio.run(_measure(gateway, ["/api/jobs/missing", "/api/chat/sessions"]))

    assert result["lag_p99_ms"] < 20, result
    assert result["health_p99_ms"] < 100, result
    # A 10 ms frame loop; Windows timers add up to ~16 ms on their own.
    assert result["frame_gap_p99_ms"] < 50, result


def test_the_probe_detects_a_handler_that_blocks_the_loop() -> None:
    """Control: an ``async def`` handler doing synchronous I/O (AL005)."""
    app = FastAPI()

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/blocking")
    async def blocking() -> dict[str, bool]:
        _blocking_io()
        return {"ok": True}

    result = asyncio.run(_measure(app, ["/blocking"]))

    assert result["lag_p99_ms"] > 150, result
