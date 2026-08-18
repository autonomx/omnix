from __future__ import annotations

import asyncio
import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import websockets
from fastapi import FastAPI


ALPACA_IEX_STREAM_URL = "wss://stream.data.alpaca.markets/v2/iex"
_STATE_KEY = "_omnix_alpaca_iex_status_monitor"
_HALT_CODES = {"2", "H", "P"}
_RESUME_CODES = {"3", "Q", "T"}


def _api_key() -> str:
    return (
        os.environ.get("OMNIX_ALPACA_API_KEY_ID")
        or os.environ.get("APCA_API_KEY_ID")
        or ""
    ).strip()


def _api_secret() -> str:
    return (
        os.environ.get("OMNIX_ALPACA_API_SECRET_KEY")
        or os.environ.get("APCA_API_SECRET_KEY")
        or ""
    ).strip()


def _enabled() -> bool:
    value = os.environ.get("OMNIX_ALPACA_STATUS_STREAM", "1").strip().lower()
    return value in {"1", "true", "yes", "on"} and bool(_api_key() and _api_secret())


@dataclass(frozen=True)
class AlpacaTradingStatus:
    symbol: str
    status_code: str
    reason_code: str | None
    message: str | None
    observed_at: datetime
    halted: bool


class AlpacaIexStatusCache:
    """Thread-safe cache of Alpaca IEX trading-status stream evidence.

    A known halt remains fail-closed even while the stream is disconnected. A
    previously observed resume is returned as authoritative only while the stream
    is connected, because a later halt could otherwise have been missed.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._values: dict[str, AlpacaTradingStatus] = {}
        self._connected = False

    def set_connected(self, connected: bool) -> None:
        with self._lock:
            self._connected = connected

    def record(self, status: AlpacaTradingStatus) -> None:
        with self._lock:
            self._values[status.symbol] = status

    def halted(self, symbol: str) -> bool | None:
        with self._lock:
            value = self._values.get(symbol.upper())
            if value is None:
                return None
            if value.halted:
                return True
            return False if self._connected else None

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "connected": self._connected,
                "symbols": len(self._values),
                "known_halts": sum(1 for item in self._values.values() if item.halted),
            }


_default_cache = AlpacaIexStatusCache()


def default_alpaca_iex_status_cache() -> AlpacaIexStatusCache:
    return _default_cache


def _parse_time(value: Any) -> datetime:
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
        else:
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


class AlpacaIexStatusMonitor:
    """Optional low-volume status stream used only to reject known trading halts."""

    def __init__(self, cache: AlpacaIexStatusCache | None = None) -> None:
        self.cache = cache or default_alpaca_iex_status_cache()
        self._task: asyncio.Task[None] | None = None
        self.last_error: str | None = None
        self.last_message_at: datetime | None = None
        self.reconnect_count = 0

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.cache.set_connected(False)

    async def _receive_control(self, socket, expected: str) -> None:
        raw = await asyncio.wait_for(socket.recv(), timeout=10)
        payload = json.loads(raw)
        messages = payload if isinstance(payload, list) else [payload]
        if not any(
            isinstance(item, dict)
            and item.get("T") == "success"
            and item.get("msg") == expected
            for item in messages
        ):
            raise RuntimeError(f"Alpaca IEX status stream did not confirm {expected}")

    async def _session(self) -> None:
        url = os.environ.get("OMNIX_ALPACA_STREAM_URL", ALPACA_IEX_STREAM_URL).strip()
        async with websockets.connect(url, ping_interval=20, close_timeout=5) as socket:
            await self._receive_control(socket, "connected")
            await socket.send(
                json.dumps(
                    {"action": "auth", "key": _api_key(), "secret": _api_secret()},
                    separators=(",", ":"),
                )
            )
            await self._receive_control(socket, "authenticated")
            await socket.send(json.dumps({"action": "subscribe", "statuses": ["*"]}))
            subscription = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
            subscription_messages = subscription if isinstance(subscription, list) else [subscription]
            if not any(
                isinstance(item, dict)
                and item.get("T") == "subscription"
                and item.get("statuses")
                for item in subscription_messages
            ):
                raise RuntimeError("Alpaca IEX status subscription was not acknowledged")
            self.cache.set_connected(True)
            async for raw in socket:
                payload = json.loads(raw)
                messages = payload if isinstance(payload, list) else [payload]
                for item in messages:
                    if not isinstance(item, dict) or item.get("T") != "s":
                        continue
                    symbol = str(item.get("S") or "").upper()
                    code = str(item.get("sc") or "").upper()
                    if not symbol or code not in _HALT_CODES | _RESUME_CODES:
                        continue
                    status = AlpacaTradingStatus(
                        symbol=symbol,
                        status_code=code,
                        reason_code=str(item.get("rc")) if item.get("rc") is not None else None,
                        message=str(item.get("sm")) if item.get("sm") is not None else None,
                        observed_at=_parse_time(item.get("t")),
                        halted=code in _HALT_CODES,
                    )
                    self.cache.record(status)
                    self.last_message_at = datetime.now(timezone.utc)

    async def _loop(self) -> None:
        delay = 1.0
        while True:
            try:
                await self._session()
                delay = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                self.reconnect_count += 1
            finally:
                self.cache.set_connected(False)
            await asyncio.sleep(delay)
            delay = min(30.0, delay * 2)

    def diagnostics(self) -> dict[str, object]:
        return {
            "enabled": _enabled(),
            "running": self._task is not None,
            "last_error": self.last_error,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "reconnect_count": self.reconnect_count,
            **self.cache.snapshot(),
        }


def register_alpaca_iex_status_monitor(gateway: FastAPI) -> AlpacaIexStatusMonitor:
    existing = getattr(gateway.state, _STATE_KEY, None)
    if isinstance(existing, AlpacaIexStatusMonitor):
        return existing
    monitor = AlpacaIexStatusMonitor()
    setattr(gateway.state, _STATE_KEY, monitor)

    async def startup() -> None:
        if _enabled():
            monitor.start()

    async def shutdown() -> None:
        await monitor.stop()

    gateway.router.add_event_handler("startup", startup)
    gateway.router.add_event_handler("shutdown", shutdown)
    return monitor
