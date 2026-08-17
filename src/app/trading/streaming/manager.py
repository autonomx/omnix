from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class StreamingBarUpdate:
    binding_id: str
    instrument_id: str
    interval: str
    start_time: datetime
    end_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    is_final: bool
    provider_event_id: str | None = None
    provider_sequence: int | None = None
    ingestion_revision: int = 1


@dataclass(slots=True)
class SharedSubscription:
    key: str
    listeners: dict[str, Callable[[StreamingBarUpdate], None]] = field(default_factory=dict)
    connected: bool = False
    reconnects: int = 0
    last_event_at: datetime | None = None


class SharedSubscriptionManager:
    """Owns one upstream logical stream for every binding/instrument/interval key."""

    def __init__(self) -> None:
        self._subscriptions: dict[str, SharedSubscription] = {}
        self._lock = threading.RLock()

    @staticmethod
    def key(binding_id: str, instrument_id: str, interval: str) -> str:
        return f"{binding_id}|{instrument_id}|{interval}"

    def subscribe(
        self,
        *,
        listener_id: str,
        binding_id: str,
        instrument_id: str,
        interval: str,
        listener: Callable[[StreamingBarUpdate], None],
    ) -> tuple[str, bool]:
        key = self.key(binding_id, instrument_id, interval)
        with self._lock:
            created = key not in self._subscriptions
            subscription = self._subscriptions.setdefault(key, SharedSubscription(key=key))
            subscription.listeners[listener_id] = listener
            return key, created

    def unsubscribe(self, key: str, listener_id: str) -> bool:
        with self._lock:
            subscription = self._subscriptions.get(key)
            if subscription is None:
                return False
            subscription.listeners.pop(listener_id, None)
            if subscription.listeners:
                return False
            self._subscriptions.pop(key, None)
            return True

    def publish(self, update: StreamingBarUpdate) -> int:
        key = self.key(update.binding_id, update.instrument_id, update.interval)
        with self._lock:
            subscription = self._subscriptions.get(key)
            listeners = tuple(subscription.listeners.values()) if subscription else ()
            if subscription:
                subscription.last_event_at = update.end_time
        for listener in listeners:
            listener(update)
        return len(listeners)

    def mark_connected(self, key: str) -> None:
        with self._lock:
            subscription = self._subscriptions[key]
            subscription.connected = True

    def mark_disconnected(self, key: str) -> None:
        with self._lock:
            subscription = self._subscriptions[key]
            subscription.connected = False
            subscription.reconnects += 1

    def status(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "key": item.key,
                    "listeners": len(item.listeners),
                    "connected": item.connected,
                    "reconnects": item.reconnects,
                    "last_event_at": item.last_event_at.isoformat() if item.last_event_at else None,
                }
                for item in self._subscriptions.values()
            ]

    @property
    def upstream_subscription_count(self) -> int:
        with self._lock:
            return len(self._subscriptions)
