"""Alert notification delivery: the outbox, the webhook sender and the delivery monitor (TVP-0.5a).

A trigger that selects a delivery channel gets one outbox row per channel, in
the transaction that records the trigger (``enqueue_alert_deliveries``). The
delivery monitor claims due rows with a lease, sends them outside any
transaction through a ``NotificationSender`` and records the result: delivered,
another attempt after an exponential backoff, or failed. Triggers stay
authoritative and delivery is at-least-once: a pass that dies between sending
and recording sends again when its lease expires, with the same delivery id
(``X-Omnix-Delivery``), so receivers can drop the duplicate.

Webhook rules:

- HTTPS only; the URL and signing secret come from the protected store by the
  alert's current reference, read when sending (never stored in PostgreSQL);
- the host is resolved once and every address checked with the strict outbound
  URL policy (no loopback, private or link-local address unless
  ``OMNIX_ALLOWED_PRIVATE_NETWORKS`` names it); the request goes to a checked
  address, with the hostname for TLS and ``Host``, so DNS cannot rebind it;
- 5 s timeout, no redirects, no proxies from the environment;
- the body is the trigger's message, ``application/json`` when it parses as
  JSON, else ``text/plain``;
- with a secret, ``X-Omnix-Signature: sha256=<hex>`` is the HMAC-SHA256 of
  ``<X-Omnix-Timestamp>.<body>``.

``last_error`` holds a reason code, never a URL, secret or response body.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Literal, Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import BaseModel

from app.config.env import environment
from app.runtime.features import FeatureContext
from app.security.tenant_context import RequestTenant, TenantContext
from app.security.url_policy import Resolver, UrlPolicyError, check_outbound_url, outbound_addresses, resolve_hostname
from app.persistence.unit_of_work import unit_of_work

from .alerts_channels import AlertWebhookStore, ProtectedAlertWebhookStore
from .monitor_task import ScheduledTradingMonitor, TradingMonitorTask

if TYPE_CHECKING:
    from .alerts import TradingAlert, TradingAlertTrigger, UnitOfWorkFactory

logger = logging.getLogger(__name__)

DeliveryChannel = Literal["webhook", "email", "push"]
DeliveryStatus = Literal["pending", "sending", "delivered", "failed"]

# Channels the outbox delivers; TVP-0.5b (email) and TVP-0.5c (push) add theirs.
OUTBOX_CHANNELS: tuple[DeliveryChannel, ...] = ("webhook",)

MAX_WEBHOOK_ATTEMPTS = 8
FIRST_RETRY_SECONDS = 30.0
MAX_RETRY_SECONDS = 3_600.0
LEASE_SECONDS = 120.0
CLAIM_BATCH = 10
WEBHOOK_TIMEOUT_SECONDS = 5.0
USER_AGENT = "Omnix-Alerts/1"


def retry_delay_seconds(attempts: int) -> float:
    """The wait before the next attempt after ``attempts`` failed ones: 30 s, 1 min, 2 min, ... at most 1 h."""
    return min(MAX_RETRY_SECONDS, FIRST_RETRY_SECONDS * 2 ** max(0, attempts - 1))


def default_alert_message(alert: TradingAlert, trigger: TradingAlertTrigger) -> str:
    return f"{alert.instrument_id}: alert {alert.alert_id} triggered at {trigger.observed_value}"


def delivery_idempotency_key(trigger_key: str, channel: str) -> str:
    return hashlib.sha256(f"{trigger_key}|{channel}".encode()).hexdigest()


def enqueue_alert_deliveries(connection: Any, workspace_id: str, alert: TradingAlert, trigger: TradingAlertTrigger) -> int:
    """Outbox rows for a new trigger, in the caller's transaction; returns how many were added.

    A webhook row is added only when the alert selects the channel and has a
    webhook. A trigger written again (same idempotency key) adds nothing.
    """
    channels = [channel for channel in OUTBOX_CHANNELS if channel in alert.parameters.notification_channels]
    if "webhook" in channels and not alert.webhook_ref:
        channels.remove("webhook")
    message = alert.parameters.message.strip() or default_alert_message(alert, trigger)
    added = 0
    for channel in channels:
        row = connection.execute(
            """
            INSERT INTO omnix_trading_notification_deliveries (
                workspace_id, delivery_id, trigger_id, alert_id, channel,
                message, max_attempts, idempotency_key
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (workspace_id, idempotency_key) DO NOTHING
            RETURNING delivery_id
            """,
            (
                workspace_id,
                uuid.uuid4().hex,
                trigger.trigger_id,
                alert.alert_id,
                channel,
                message,
                MAX_WEBHOOK_ATTEMPTS,
                delivery_idempotency_key(trigger.idempotency_key, channel),
            ),
        ).fetchone()
        added += row is not None
    return added


class NotificationDelivery(BaseModel):
    """A delivery as the API shows it: status only, never a destination."""

    delivery_id: str
    trigger_id: str
    alert_id: str
    channel: DeliveryChannel
    status: DeliveryStatus
    attempts: int
    max_attempts: int
    next_attempt_at: datetime | None
    last_attempt_at: datetime | None
    last_error: str | None
    last_status_code: int | None
    delivered_at: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class ClaimedDelivery:
    """A delivery leased to one send. ``attempt`` fences the result: a stale sender's result is ignored."""

    delivery_id: str
    trigger_id: str
    alert_id: str
    channel: str
    message: str
    attempt: int
    max_attempts: int
    webhook_ref: str | None


@dataclass(frozen=True)
class DeliveryResult:
    outcome: Literal["delivered", "retry", "failed"]
    error: str | None = None
    status_code: int | None = None
    # Seconds the destination asked to wait (Retry-After), honoured up to the backoff ceiling.
    retry_after: float | None = None


class NotificationSender(Protocol):
    """Sends one claimed delivery; the port lets delivery move to the platform tier later."""

    def send(self, delivery: ClaimedDelivery) -> DeliveryResult: ...


_DELIVERY_COLUMNS = """
    delivery_id, trigger_id, alert_id, channel, status, attempts, max_attempts,
    next_attempt_at, last_attempt_at, last_error, last_status_code, delivered_at, created_at
"""


def _delivery(row: Any) -> NotificationDelivery:
    status = str(row[4])
    return NotificationDelivery(
        delivery_id=str(row[0]),
        trigger_id=str(row[1]),
        alert_id=str(row[2]),
        channel=row[3],
        status=row[4],
        attempts=int(row[5]),
        max_attempts=int(row[6]),
        next_attempt_at=row[7] if status == "pending" else None,
        last_attempt_at=row[8],
        last_error=row[9],
        last_status_code=row[10],
        delivered_at=row[11],
        created_at=row[12],
    )


class NotificationDeliveryRepository:
    context = RequestTenant()

    def __init__(self, *, context: TenantContext | None = None, uow_factory: UnitOfWorkFactory = unit_of_work) -> None:
        self.context = context
        self.uow_factory = uow_factory

    def claim_due(self, now: datetime, *, limit: int = CLAIM_BATCH, lease_seconds: float = LEASE_SECONDS) -> list[ClaimedDelivery]:
        """Leases due deliveries: pending ones whose time has come and sends whose lease ran out."""
        with self.uow_factory() as uow:
            rows = uow.connection.execute(
                """
                WITH due AS (
                    SELECT workspace_id, delivery_id
                      FROM omnix_trading_notification_deliveries
                     WHERE workspace_id = %s
                       AND ((status = 'pending' AND next_attempt_at <= %s)
                            OR (status = 'sending' AND lease_expires_at <= %s))
                     ORDER BY next_attempt_at, delivery_id
                     LIMIT %s
                     FOR UPDATE SKIP LOCKED
                )
                UPDATE omnix_trading_notification_deliveries AS delivery
                   SET status = 'sending',
                       attempts = delivery.attempts + 1,
                       lease_expires_at = %s,
                       last_attempt_at = %s,
                       updated_at = %s
                  FROM due
                 WHERE delivery.workspace_id = due.workspace_id AND delivery.delivery_id = due.delivery_id
                RETURNING delivery.delivery_id, delivery.trigger_id, delivery.alert_id, delivery.channel,
                          delivery.message, delivery.attempts, delivery.max_attempts,
                          (SELECT alert.notification_settings->>'webhook_ref'
                             FROM omnix_trading_alerts AS alert
                            WHERE alert.workspace_id = delivery.workspace_id AND alert.alert_id = delivery.alert_id)
                """,
                (
                    self.context.workspace_id,
                    now,
                    now,
                    limit,
                    now + timedelta(seconds=lease_seconds),
                    now,
                    now,
                ),
            ).fetchall()
            uow.commit()
        claimed = [
            ClaimedDelivery(
                delivery_id=str(row[0]),
                trigger_id=str(row[1]),
                alert_id=str(row[2]),
                channel=str(row[3]),
                message=str(row[4]),
                attempt=int(row[5]),
                max_attempts=int(row[6]),
                webhook_ref=str(row[7]) if row[7] else None,
            )
            for row in rows
        ]
        return sorted(claimed, key=lambda item: item.delivery_id)

    def record(self, delivery: ClaimedDelivery, result: DeliveryResult, now: datetime) -> DeliveryStatus | None:
        """Records one send. Returns the new status, or None when the lease was lost (another pass owns the row)."""
        if result.outcome == "delivered":
            status: DeliveryStatus = "delivered"
        elif result.outcome == "retry" and delivery.attempt < delivery.max_attempts:
            status = "pending"
        else:
            status = "failed"
        delay = retry_delay_seconds(delivery.attempt)
        if result.retry_after is not None:
            delay = min(MAX_RETRY_SECONDS, max(delay, result.retry_after))
        error = result.error if status != "delivered" else None
        if status == "failed" and result.outcome == "retry":
            error = f"{result.error or 'retry'}:attempts_exhausted"
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                """
                UPDATE omnix_trading_notification_deliveries
                   SET status = %s,
                       lease_expires_at = NULL,
                       next_attempt_at = CASE WHEN %s = 'pending' THEN %s ELSE next_attempt_at END,
                       last_error = %s,
                       last_status_code = %s,
                       delivered_at = CASE WHEN %s = 'delivered' THEN %s ELSE NULL END,
                       updated_at = %s
                 WHERE workspace_id = %s AND delivery_id = %s
                   AND status = 'sending' AND attempts = %s
                RETURNING status
                """,
                (
                    status,
                    status,
                    now + timedelta(seconds=delay),
                    error,
                    result.status_code,
                    status,
                    now,
                    now,
                    self.context.workspace_id,
                    delivery.delivery_id,
                    delivery.attempt,
                ),
            ).fetchone()
            uow.commit()
        return status if row is not None else None

    def list_deliveries(self, *, alert_id: str | None = None, limit: int = 100) -> list[NotificationDelivery]:
        with self.uow_factory() as uow:
            rows = uow.connection.execute(
                f"""
                SELECT {_DELIVERY_COLUMNS}
                  FROM omnix_trading_notification_deliveries
                 WHERE workspace_id = %s AND (%s::TEXT IS NULL OR alert_id = %s)
                 ORDER BY created_at DESC, delivery_id
                 LIMIT %s
                """,
                (self.context.workspace_id, alert_id, alert_id, limit),
            ).fetchall()
            return [_delivery(row) for row in rows]


def default_delivery_repository() -> NotificationDeliveryRepository:
    return NotificationDeliveryRepository()


def _signature(secret: str, timestamp: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), timestamp.encode("ascii") + b"." + body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _content_type(message: str) -> str:
    try:
        json.loads(message)
    except ValueError:
        return "text/plain; charset=utf-8"
    return "application/json"


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after", "").strip()
    if value.isdigit():
        return float(value)
    return None


def _pinned_url(url: str, address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    parts = urlsplit(url)
    host = f"[{address}]" if address.version == 6 else str(address)
    netloc = f"{host}:{parts.port}" if parts.port else host
    return urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, ""))


def _host_header(url: str) -> str:
    parts = urlsplit(url)
    hostname = parts.hostname or ""
    host = f"[{hostname}]" if ":" in hostname else hostname
    return f"{host}:{parts.port}" if parts.port else host


class WebhookSender:
    """Sends a delivery to its alert's webhook."""

    def __init__(
        self,
        store: AlertWebhookStore | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        resolver: Resolver = resolve_hostname,
        timeout: float = WEBHOOK_TIMEOUT_SECONDS,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.store = store or ProtectedAlertWebhookStore()
        self.transport = transport
        self.resolver = resolver
        self.timeout = timeout
        self.clock = clock

    def send(self, delivery: ClaimedDelivery) -> DeliveryResult:
        if not delivery.webhook_ref:
            return DeliveryResult("failed", "webhook_missing")
        try:
            stored = self.store.load(delivery.webhook_ref)
        except Exception:
            # Never mistake an unreadable store for a removed webhook.
            logger.warning("trading_alert_webhook_store_unreadable delivery_id=%s", delivery.delivery_id)
            return DeliveryResult("retry", "webhook_store_unavailable")
        if not stored or not stored.get("url"):
            return DeliveryResult("failed", "webhook_missing")
        url = stored["url"]
        try:
            check_outbound_url(url, strict=True, https_only=True)
            addresses = outbound_addresses(url, strict=True, resolver=self.resolver)
        except UrlPolicyError as exc:
            reason = str(exc)
            if reason == "hostname_resolution_failed":
                return DeliveryResult("retry", "dns_failed")
            return DeliveryResult("failed", f"url_policy:{reason}")
        body = delivery.message.encode("utf-8")
        timestamp = str(int(self.clock().timestamp()))
        headers = {
            "Host": _host_header(url),
            "Content-Type": _content_type(delivery.message),
            "User-Agent": USER_AGENT,
            "X-Omnix-Delivery": delivery.delivery_id,
            "X-Omnix-Alert": delivery.alert_id,
            "X-Omnix-Timestamp": timestamp,
        }
        secret = stored.get("secret", "")
        if secret:
            headers["X-Omnix-Signature"] = _signature(secret, timestamp, body)
        hostname = urlsplit(url).hostname or ""
        try:
            with httpx.Client(
                transport=self.transport,
                timeout=self.timeout,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = client.post(
                    _pinned_url(url, addresses[0]),
                    content=body,
                    headers=headers,
                    extensions={"sni_hostname": hostname},
                )
        except httpx.TimeoutException:
            return DeliveryResult("retry", "timeout")
        except httpx.HTTPError:
            return DeliveryResult("retry", "connection_failed")
        code = response.status_code
        if 200 <= code < 300:
            return DeliveryResult("delivered", status_code=code)
        if 300 <= code < 400:
            return DeliveryResult("failed", "redirect_refused", code)
        if code in {408, 425, 429} or code >= 500:
            return DeliveryResult("retry", f"http_{code}", code, _retry_after(response))
        return DeliveryResult("failed", f"http_{code}", code)


def _env_flag(name: str, default: str) -> bool:
    return environment().get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def notification_delivery_monitor_enabled() -> bool:
    if environment().get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return _env_flag("OMNIX_TRADING_NOTIFICATION_MONITOR_IN_TESTS", "0")
    return _env_flag("OMNIX_TRADING_NOTIFICATION_MONITOR", "1")


class NotificationDeliveryMonitor(ScheduledTradingMonitor):
    def __init__(
        self,
        *,
        repository_factory: Callable[[], NotificationDeliveryRepository] = default_delivery_repository,
        senders: Mapping[str, NotificationSender] | None = None,
        interval_seconds: float = 10.0,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.repository_factory = repository_factory
        self.senders: Mapping[str, NotificationSender] = senders if senders is not None else {"webhook": WebhookSender()}
        self.interval_seconds = interval_seconds
        self.clock = clock
        self.last_error: str | None = None
        self.last_run_at: datetime | None = None
        self.counts: dict[str, int] = {"delivered": 0, "pending": 0, "failed": 0, "lease_lost": 0}

    async def run_once(self) -> int:
        repository = self.repository_factory()
        error: str | None = None
        delivered = 0
        try:
            claimed = await asyncio.to_thread(repository.claim_due, self.clock())
        except Exception as exc:
            claimed = []
            error = f"{type(exc).__name__}: {exc}"
        for delivery in claimed:
            sender = self.senders.get(delivery.channel)
            try:
                if sender is None:
                    result = DeliveryResult("failed", "channel_unavailable")
                else:
                    result = await asyncio.to_thread(sender.send, delivery)
            except Exception as exc:
                logger.exception("trading_notification_send_failed delivery_id=%s", delivery.delivery_id)
                result = DeliveryResult("retry", f"sender_error:{type(exc).__name__}")
            try:
                status = await asyncio.to_thread(repository.record, delivery, result, self.clock())
            except Exception as exc:
                # The lease runs out and the delivery is sent again: at-least-once.
                error = f"{type(exc).__name__}: {exc}"
                continue
            key = status or "lease_lost"
            self.counts[key] = self.counts.get(key, 0) + 1
            delivered += status == "delivered"
        self.last_error = error
        self.last_run_at = datetime.now(timezone.utc)
        return delivered

    def diagnostics(self) -> dict[str, Any]:
        return {
            "enabled": notification_delivery_monitor_enabled(),
            "running": self.scheduled,
            "interval_seconds": self.interval_seconds,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_error": self.last_error,
            "counts": dict(self.counts),
        }


_MONITOR_STATE_KEY = "_omnix_trading_notification_delivery_monitor"


def create_notification_delivery_monitor_task(context: FeatureContext) -> TradingMonitorTask | None:
    state = context.runtime_state
    if isinstance(getattr(state, _MONITOR_STATE_KEY, None), NotificationDeliveryMonitor):
        return None
    monitor = NotificationDeliveryMonitor()
    setattr(state, _MONITOR_STATE_KEY, monitor)
    return TradingMonitorTask(name=__name__, monitor=monitor, enabled=notification_delivery_monitor_enabled)


__all__ = [
    "ClaimedDelivery",
    "DeliveryResult",
    "NotificationDelivery",
    "NotificationDeliveryMonitor",
    "NotificationDeliveryRepository",
    "NotificationSender",
    "OUTBOX_CHANNELS",
    "WebhookSender",
    "create_notification_delivery_monitor_task",
    "delivery_idempotency_key",
    "enqueue_alert_deliveries",
    "retry_delay_seconds",
]
