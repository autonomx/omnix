"""Alert notification channels: which ones have a sender, and webhook secrets (TVP-1.2).

``notification_channels`` accepts every channel the schema knows, but an alert
may only select a channel whose sender is deployed. TVP-0.5a (webhook),
TVP-0.5b (email) and TVP-0.5c (push) each add theirs to
``AVAILABLE_ALERT_CHANNELS`` without a migration.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from app.security.provider_secret_store import (
    has_alert_webhook_secret,
    save_alert_webhook_secret,
)

AVAILABLE_ALERT_CHANNELS: frozenset[str] = frozenset({"app", "toast", "sound"})


def unavailable_channels(channels: Iterable[str], available: Iterable[str] = AVAILABLE_ALERT_CHANNELS) -> list[str]:
    allowed = set(available)
    return [channel for channel in dict.fromkeys(channels) if channel not in allowed]


class AlertSecretStore(Protocol):
    def save(self, workspace_id: str, alert_id: str, secret: str | None) -> None: ...
    def has(self, workspace_id: str, alert_id: str) -> bool: ...


def _key(workspace_id: str, alert_id: str) -> str:
    return f"{workspace_id}/{alert_id}"


class ProtectedAlertSecretStore:
    """Webhook secrets in the user's OS-protected provider secret store, never in PostgreSQL."""

    def save(self, workspace_id: str, alert_id: str, secret: str | None) -> None:
        save_alert_webhook_secret(_key(workspace_id, alert_id), secret)

    def has(self, workspace_id: str, alert_id: str) -> bool:
        return has_alert_webhook_secret(_key(workspace_id, alert_id))


__all__ = [
    "AVAILABLE_ALERT_CHANNELS",
    "AlertSecretStore",
    "ProtectedAlertSecretStore",
    "unavailable_channels",
]
