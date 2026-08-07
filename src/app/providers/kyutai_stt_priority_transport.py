"""Prioritize Kyutai transcript events over high-rate endpoint telemetry.

The Kyutai model can run faster than real time on a local GPU. Its provider emits one
semantic endpoint score per model step, while words/partials share the same browser
WebSocket. Serially awaiting every score can therefore create head-of-line blocking:
the provider transcript is already updated, but the browser has not yet received the
partial that corresponds to it.

This module keeps endpoint telemetry lossy/coalesced while preserving transcript,
finalization, replay, and error messages exactly. A pending endpoint candidate is
flushed immediately after a partial so browser-side speculation never observes a
candidate before the transcript that made the candidate eligible.
"""
from __future__ import annotations

import asyncio
import os
import weakref
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from fastapi import WebSocket

from app.providers import kyutai_stt_websocket as _bridge

SafeSend = Callable[[WebSocket, asyncio.Lock, dict[str, Any]], Awaitable[bool]]
DEFAULT_ENDPOINT_TELEMETRY_INTERVAL_MS = 20.0
MIN_ENDPOINT_TELEMETRY_INTERVAL_MS = 5.0
MAX_ENDPOINT_TELEMETRY_INTERVAL_MS = 100.0


@dataclass
class _PendingTelemetry:
    latest_score: dict[str, Any] | None = None
    latest_candidate: dict[str, Any] | None = None
    flush_task: asyncio.Task[None] | None = None


class KyutaiPrioritySender:
    """Coalesce endpoint telemetry without delaying transcript-bearing messages."""

    def __init__(
        self,
        send_immediately: SafeSend,
        *,
        interval_ms: float = DEFAULT_ENDPOINT_TELEMETRY_INTERVAL_MS,
    ) -> None:
        self._send_immediately = send_immediately
        self._interval_seconds = max(
            MIN_ENDPOINT_TELEMETRY_INTERVAL_MS,
            min(MAX_ENDPOINT_TELEMETRY_INTERVAL_MS, float(interval_ms)),
        ) / 1000.0
        self._states: weakref.WeakKeyDictionary[WebSocket, _PendingTelemetry] = (
            weakref.WeakKeyDictionary()
        )

    async def send(
        self,
        websocket: WebSocket,
        lock: asyncio.Lock,
        payload: dict[str, Any],
    ) -> bool:
        message_type = str(payload.get("type", ""))
        state = self._states.setdefault(websocket, _PendingTelemetry())

        if message_type == "endpoint_score":
            state.latest_score = dict(payload)
            self._schedule_flush(websocket, lock, state)
            return True

        if message_type == "endpoint_candidate":
            state.latest_candidate = dict(payload)
            self._schedule_flush(websocket, lock, state)
            return True

        # Transcript delivery is authoritative for downstream semantic assessment
        # and speculative generation. Send it first, then release the newest
        # candidate/score that may have been queued ahead of the provider Word.
        sent = await self._send_immediately(websocket, lock, payload)
        if message_type == "partial" and sent:
            telemetry_sent = await self._flush_now(websocket, lock, state)
            return sent and telemetry_sent
        return sent

    def _schedule_flush(
        self,
        websocket: WebSocket,
        lock: asyncio.Lock,
        state: _PendingTelemetry,
    ) -> None:
        if state.flush_task is not None and not state.flush_task.done():
            return

        async def delayed_flush() -> None:
            try:
                await asyncio.sleep(self._interval_seconds)
                await self._flush_now(websocket, lock, state, cancel_timer=False)
            except asyncio.CancelledError:
                return

        state.flush_task = asyncio.create_task(delayed_flush())

    async def _flush_now(
        self,
        websocket: WebSocket,
        lock: asyncio.Lock,
        state: _PendingTelemetry,
        *,
        cancel_timer: bool = True,
    ) -> bool:
        timer = state.flush_task
        current = asyncio.current_task()
        if cancel_timer and timer is not None and timer is not current and not timer.done():
            timer.cancel()
        state.flush_task = None

        # Candidate first: after a partial is visible, it is the latency-critical
        # control message. Endpoint scores are diagnostics/continuous authority input
        # and may safely be coalesced to the newest value.
        pending = (state.latest_candidate, state.latest_score)
        state.latest_candidate = None
        state.latest_score = None
        ok = True
        for item in pending:
            if item is not None:
                ok = await self._send_immediately(websocket, lock, item) and ok
        if not ok:
            self._states.pop(websocket, None)
        return ok


def install_kyutai_stt_priority_transport() -> None:
    """Install the coalescing sender once for the standalone Kyutai adapter."""

    if getattr(_bridge, "_omnix_priority_transport_installed", False):
        return
    original = _bridge._safe_send
    configured_interval = float(
        os.environ.get(
            "KYUTAI_BROWSER_ENDPOINT_TELEMETRY_INTERVAL_MS",
            str(DEFAULT_ENDPOINT_TELEMETRY_INTERVAL_MS),
        )
    )
    sender = KyutaiPrioritySender(original, interval_ms=configured_interval)
    _bridge._safe_send = sender.send
    _bridge._omnix_priority_transport_installed = True
    _bridge._omnix_priority_transport_sender = sender
