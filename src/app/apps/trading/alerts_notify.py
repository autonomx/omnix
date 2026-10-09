"""Alert email (TVP-0.5b) and web-push (TVP-0.5c) delivery: settings, subscriptions and the two senders.

Both run behind the notification outbox (``alerts_delivery.py``): the monitor claims a delivery and hands it to the
sender of its channel, which returns delivered, retry or failed.

- **Email:** a workspace's SMTP server (STARTTLS or TLS; plain only without a login), sender and up to five
  recipients. The password lives in the OS-protected secret store, never in PostgreSQL. The server's address is
  checked like a webhook's (no private, loopback or link-local address unless ``OMNIX_ALLOWED_PRIVATE_NETWORKS``
  allows it) and the connection goes to that checked address.
- **Web push:** each browser that allows notifications subscribes with Omnix's VAPID key (made once, kept in the
  secret store) and stores its subscription per user and device. A push carries the alert's message, encrypted for
  that browser (``webpush.py``); a subscription the push service says is gone (404, 410) is removed.
"""

from __future__ import annotations

import json
import logging
import re
import smtplib
import socket
import ssl
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, Field, field_validator, model_validator

from app.config.env import env_str
from app.persistence.tenant_scope import system_scope
from app.persistence.unit_of_work import unit_of_work
from app.security.provider_secret_store import (
    delete_alert_notification_secret,
    load_alert_notification_secret,
    save_alert_notification_secret,
)
from app.security.tenant_context import RequestTenant, TenantContext
from app.security.url_policy import Resolver, UrlPolicyError, check_outbound_url, outbound_addresses, resolve_hostname

from .alerts_delivery import (
    DNS_TIMEOUT_SECONDS,
    SEND_DEADLINE_SECONDS,
    SYSTEM_OPERATION,
    USER_AGENT,
    ClaimedDelivery,
    DeliveryResult,
    _ascii_url,
    _Deadline,
    _host_header,
    _pinned_url,
    bounded,
    post_within,
)
from .webpush import MAX_PLAINTEXT, encrypt_push, load_vapid_key, new_vapid_key, vapid_authorization

logger = logging.getLogger(__name__)

EMAIL_PATTERN = re.compile(r"^[^@\s<>\"]+@[^@\s<>\"]+\.[^@\s<>\"]+$")
SMTP_TIMEOUT_SECONDS = 10.0
VAPID_SECRET = "webpush/vapid_private_key"
# Push messages live this long at the push service while a device is offline.
PUSH_TTL_SECONDS = 24 * 3600
MAX_SUBSCRIPTIONS_PER_USER = 20


def smtp_password_secret(workspace_id: str) -> str:
    return f"smtp/{workspace_id}/password"


class NotificationSecretStore(Protocol):
    def available(self) -> bool: ...
    def load(self, name: str) -> str | None: ...
    def save(self, name: str, value: str) -> None: ...
    def delete(self, name: str) -> None: ...


class ProtectedNotificationSecretStore:
    """Delivery credentials in the user's OS-protected provider secret store (DPAPI), like webhooks."""

    def available(self) -> bool:
        import sys

        return sys.platform == "win32"

    def load(self, name: str) -> str | None:
        return load_alert_notification_secret(name)

    def save(self, name: str, value: str) -> None:
        save_alert_notification_secret(name, value)

    def delete(self, name: str) -> None:
        delete_alert_notification_secret(name)


# --- Settings ----------------------------------------------------------------------------------------------------


class EmailSettings(BaseModel):
    """A workspace's SMTP server, as stored and shown (the password is only ``has_password``)."""

    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=587, ge=1, le=65535)
    security: Literal["starttls", "tls", "none"] = "starttls"
    username: str = Field(default="", max_length=320)
    from_address: str = Field(min_length=3, max_length=320)
    to_addresses: list[str] = Field(min_length=1, max_length=5)
    has_password: bool = False

    @field_validator("host")
    @classmethod
    def _host(cls, value: str) -> str:
        host = value.strip().lower().rstrip(".")
        if not re.fullmatch(r"[a-z0-9.\-]+|\[[0-9a-f:]+\]", host):
            raise ValueError("the SMTP host is a hostname or an IP address")
        return host

    @field_validator("from_address")
    @classmethod
    def _from(cls, value: str) -> str:
        if not EMAIL_PATTERN.match(value.strip()):
            raise ValueError("the sender is an email address")
        return value.strip()

    @field_validator("to_addresses")
    @classmethod
    def _to(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not EMAIL_PATTERN.match(value) for value in cleaned):
            raise ValueError("each recipient is an email address")
        return list(dict.fromkeys(cleaned))


class EmailSettingsWrite(EmailSettings):
    """``password``: None keeps the stored one, an empty string removes it."""

    password: str | None = Field(default=None, max_length=500, exclude=True)
    has_password: bool = Field(default=False, exclude=True)

    @model_validator(mode="after")
    def _login_needs_tls(self) -> EmailSettingsWrite:
        if self.username and self.security == "none":
            raise ValueError("a login needs STARTTLS or TLS; a password is never sent in the clear")
        return self


class PushSubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=80, max_length=120)
    auth: str = Field(min_length=16, max_length=64)


class PushSubscriptionWrite(BaseModel):
    endpoint: str = Field(min_length=12, max_length=2000)
    keys: PushSubscriptionKeys
    user_agent: str = Field(default="", max_length=300)


class PushSubscription(BaseModel):
    """A subscription as the API shows it: no endpoint or keys, only the push service's host."""

    subscription_id: str
    user_id: str
    service: str
    user_agent: str
    created_at: datetime
    last_success_at: datetime | None = None


@dataclass(frozen=True)
class StoredSubscription:
    subscription_id: str
    user_id: str
    endpoint: str
    p256dh: str
    auth: str


class NotificationSettingsRepository:
    """Email settings and push subscriptions; ``all_workspaces`` (the senders) reads any workspace by id."""

    context = RequestTenant()

    def __init__(self, *, context: TenantContext | None = None, uow_factory: Callable[[], Any] = unit_of_work, all_workspaces: bool = False) -> None:
        self.context = context
        self.uow_factory = uow_factory
        self.all_workspaces = all_workspaces

    @contextmanager
    def _work(self) -> Iterator[Any]:
        with system_scope(SYSTEM_OPERATION) if self.all_workspaces else nullcontext(), self.uow_factory() as uow:
            yield uow

    def _workspace(self, workspace_id: str | None) -> str:
        return workspace_id if self.all_workspaces and workspace_id else self.context.workspace_id

    def email(self, workspace_id: str | None = None) -> EmailSettings | None:
        with self._work() as uow:
            row = uow.connection.execute(
                "SELECT email FROM omnix_trading_notification_settings WHERE workspace_id = %s", (self._workspace(workspace_id),),
            ).fetchone()
        return EmailSettings.model_validate(row[0]) if row and row[0] else None

    def save_email(self, settings: EmailSettings | None) -> None:
        payload = json.dumps(settings.model_dump(mode="json")) if settings is not None else None
        with self._work() as uow:
            uow.connection.execute(
                """
                INSERT INTO omnix_trading_notification_settings (workspace_id, email) VALUES (%s, %s::jsonb)
                ON CONFLICT (workspace_id) DO UPDATE SET email = EXCLUDED.email, updated_at = CURRENT_TIMESTAMP
                """,
                (self._workspace(None), payload),
            )
            uow.commit()

    def subscriptions(self, workspace_id: str | None = None, *, user_id: str | None = None) -> list[StoredSubscription]:
        with self._work() as uow:
            rows = uow.connection.execute(
                """
                SELECT subscription_id, user_id, endpoint, p256dh, auth FROM omnix_trading_push_subscriptions
                 WHERE workspace_id = %s AND (%s::TEXT IS NULL OR user_id = %s)
                 ORDER BY created_at, subscription_id
                """,
                (self._workspace(workspace_id), user_id, user_id),
            ).fetchall()
        return [StoredSubscription(str(row[0]), str(row[1]), str(row[2]), str(row[3]), str(row[4])) for row in rows]

    def listed_subscriptions(self) -> list[PushSubscription]:
        with self._work() as uow:
            rows = uow.connection.execute(
                """
                SELECT subscription_id, user_id, endpoint, user_agent, created_at, last_success_at FROM omnix_trading_push_subscriptions
                 WHERE workspace_id = %s ORDER BY created_at, subscription_id
                """,
                (self._workspace(None),),
            ).fetchall()
        return [
            PushSubscription(subscription_id=str(row[0]), user_id=str(row[1]), service=urlsplit(str(row[2])).hostname or "",
                             user_agent=str(row[3]), created_at=row[4], last_success_at=row[5])
            for row in rows
        ]

    def save_subscription(self, user_id: str, subscription: PushSubscriptionWrite) -> str:
        """Add or refresh this browser's subscription (by endpoint); returns its id."""
        with self._work() as uow:
            count = uow.connection.execute(
                "SELECT count(*) FROM omnix_trading_push_subscriptions WHERE workspace_id = %s AND user_id = %s AND endpoint <> %s",
                (self._workspace(None), user_id, subscription.endpoint),
            ).fetchone()
            if count and int(count[0]) >= MAX_SUBSCRIPTIONS_PER_USER:
                raise ValueError(f"at most {MAX_SUBSCRIPTIONS_PER_USER} devices per person get notifications")
            row = uow.connection.execute(
                """
                INSERT INTO omnix_trading_push_subscriptions (workspace_id, subscription_id, user_id, endpoint, p256dh, auth, user_agent)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (workspace_id, endpoint) DO UPDATE
                   SET user_id = EXCLUDED.user_id, p256dh = EXCLUDED.p256dh, auth = EXCLUDED.auth, user_agent = EXCLUDED.user_agent
                RETURNING subscription_id
                """,
                (self._workspace(None), uuid.uuid4().hex, user_id, subscription.endpoint, subscription.keys.p256dh,
                 subscription.keys.auth, subscription.user_agent),
            ).fetchone()
            uow.commit()
        return str(row[0])

    def delete_subscription(self, subscription_id: str, workspace_id: str | None = None) -> bool:
        with self._work() as uow:
            row = uow.connection.execute(
                "DELETE FROM omnix_trading_push_subscriptions WHERE workspace_id = %s AND subscription_id = %s RETURNING subscription_id",
                (self._workspace(workspace_id), subscription_id),
            ).fetchone()
            uow.commit()
        return row is not None

    def mark_delivered(self, subscription_id: str, workspace_id: str | None = None) -> None:
        with self._work() as uow:
            uow.connection.execute(
                "UPDATE omnix_trading_push_subscriptions SET last_success_at = CURRENT_TIMESTAMP WHERE workspace_id = %s AND subscription_id = %s",
                (self._workspace(workspace_id), subscription_id),
            )
            uow.commit()


def default_notification_settings_repository() -> NotificationSettingsRepository:
    return NotificationSettingsRepository()


def sender_settings_repository() -> NotificationSettingsRepository:
    return NotificationSettingsRepository(all_workspaces=True)


# --- Email -------------------------------------------------------------------------------------------------------


class _PinnedSMTP(smtplib.SMTP):
    """SMTP to a checked address, keeping the hostname for STARTTLS certificate checks."""

    def __init__(self, hostname: str, address: str, port: int, timeout: float) -> None:
        self._pinned = address
        super().__init__(timeout=timeout)
        self._host = hostname
        self.connect(hostname, port)

    def _get_socket(self, host: str, port: int, timeout: float) -> socket.socket:
        return socket.create_connection((self._pinned, port), timeout)


class _PinnedSMTPSSL(smtplib.SMTP_SSL):
    def __init__(self, hostname: str, address: str, port: int, timeout: float, context: ssl.SSLContext) -> None:
        self._pinned = address
        super().__init__(timeout=timeout, context=context)
        self._host = hostname
        self.connect(hostname, port)

    def _get_socket(self, host: str, port: int, timeout: float) -> socket.socket:
        raw = socket.create_connection((self._pinned, port), timeout)
        return self.context.wrap_socket(raw, server_hostname=self._host)


SmtpFactory = Callable[[EmailSettings, str], smtplib.SMTP]


def default_smtp_factory(settings: EmailSettings, address: str) -> smtplib.SMTP:
    context = ssl.create_default_context()
    if settings.security == "tls":
        return _PinnedSMTPSSL(settings.host, address, settings.port, SMTP_TIMEOUT_SECONDS, context)
    client = _PinnedSMTP(settings.host, address, settings.port, SMTP_TIMEOUT_SECONDS)
    if settings.security == "starttls":
        client.starttls(context=context)
    return client


def alert_email(settings: EmailSettings, message: str, *, alert_id: str = "", test: bool = False) -> EmailMessage:
    first_line = (message.strip().splitlines() or [""])[0][:120]
    email = EmailMessage()
    email["Subject"] = "Omnix test notification" if test else f"Omnix alert: {first_line or alert_id}"
    email["From"] = settings.from_address
    email["To"] = ", ".join(settings.to_addresses)
    email["X-Omnix-Alert"] = alert_id or "test"
    email.set_content(f"{message.strip()}\n\n— Omnix alerts{f' ({alert_id})' if alert_id else ''}\n")
    return email


class EmailSender:
    """Sends a delivery by its workspace's SMTP settings."""

    def __init__(
        self,
        repository_factory: Callable[[], NotificationSettingsRepository] = sender_settings_repository,
        store: NotificationSecretStore | None = None,
        *,
        smtp_factory: SmtpFactory = default_smtp_factory,
        resolver: Resolver = resolve_hostname,
    ) -> None:
        self.repository_factory = repository_factory
        self.store = store or ProtectedNotificationSecretStore()
        self.smtp_factory = smtp_factory
        self.resolver = resolver

    def send(self, delivery: ClaimedDelivery) -> DeliveryResult:
        settings = self.repository_factory().email(delivery.workspace_id)
        if settings is None:
            return DeliveryResult("failed", "email_not_configured")
        return self.deliver(settings, delivery.workspace_id, alert_email(settings, delivery.message, alert_id=delivery.alert_id))

    def deliver(self, settings: EmailSettings, workspace_id: str, message: EmailMessage) -> DeliveryResult:
        password = None
        if settings.username:
            try:
                password = self.store.load(smtp_password_secret(workspace_id))
            except Exception:
                logger.warning("trading_alert_smtp_secret_unreadable workspace_id=%s", workspace_id)
                return DeliveryResult("retry", "secret_store_unavailable")
            if not password:
                return DeliveryResult("failed", "email_password_missing")
        try:
            host = f"[{settings.host.strip('[]')}]" if ":" in settings.host else settings.host
            addresses = outbound_addresses(f"https://{host}:{settings.port}/", strict=True, resolver=bounded(self.resolver, DNS_TIMEOUT_SECONDS))
        except _Deadline:
            return DeliveryResult("retry", "dns_timeout")
        except UrlPolicyError as exc:
            return DeliveryResult("retry", "dns_failed") if str(exc) == "hostname_resolution_failed" else DeliveryResult("failed", f"url_policy:{exc}")
        error = "connection_failed"
        for address in addresses[:3]:
            try:
                client = self.smtp_factory(settings, str(address))
            except (OSError, smtplib.SMTPException):
                continue
            try:
                if settings.username and password:
                    client.login(settings.username, password)
                client.send_message(message)
                return DeliveryResult("delivered")
            except smtplib.SMTPAuthenticationError:
                return DeliveryResult("failed", "smtp_auth_failed")
            except smtplib.SMTPRecipientsRefused:
                return DeliveryResult("failed", "smtp_recipients_refused")
            except smtplib.SMTPSenderRefused:
                return DeliveryResult("failed", "smtp_sender_refused")
            except smtplib.SMTPResponseException as exc:
                return DeliveryResult("failed" if exc.smtp_code >= 500 else "retry", f"smtp_{exc.smtp_code}")
            except (OSError, smtplib.SMTPException):
                error = "connection_failed"
            finally:
                try:
                    client.quit()
                except (OSError, smtplib.SMTPException):
                    pass
        return DeliveryResult("retry", error)


# --- Web push ----------------------------------------------------------------------------------------------------


def vapid_subject() -> str:
    """The contact push services may use about Omnix's pushes (``OMNIX_VAPID_SUBJECT``: mailto: or https:)."""
    subject = (env_str("OMNIX_VAPID_SUBJECT", "") or "").strip()
    return subject if subject.startswith(("mailto:", "https://")) else "mailto:alerts@omnix.invalid"


def vapid_key(store: NotificationSecretStore, *, create: bool) -> Any:
    """Omnix's VAPID key; made and stored on first use when ``create``. None without one (or without a store)."""
    pem = store.load(VAPID_SECRET)
    if not pem and create:
        if not store.available():
            return None
        pem = new_vapid_key()
        store.save(VAPID_SECRET, pem)
    return load_vapid_key(pem) if pem else None


def push_payload(message: str, *, alert_id: str = "", trigger_id: str = "", title: str = "Omnix alert") -> bytes:
    """What a browser shows: a title, the message (cut to fit a push) and where a click goes."""
    body = message.strip()
    payload = {"title": title, "body": body, "alert_id": alert_id, "trigger_id": trigger_id, "url": "/trading" + (f"?alert={alert_id}" if alert_id else "")}
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    while len(encoded) > MAX_PLAINTEXT and payload["body"]:
        payload["body"] = payload["body"][: max(0, len(payload["body"]) - (len(encoded) - MAX_PLAINTEXT) - 1)].rstrip() + "…"
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return encoded


class PushSender:
    """Sends a delivery to every browser subscribed in its workspace."""

    def __init__(
        self,
        repository_factory: Callable[[], NotificationSettingsRepository] = sender_settings_repository,
        store: NotificationSecretStore | None = None,
        *,
        exchange: Callable[[httpx.Request, float], httpx.Response] = post_within,
        resolver: Resolver = resolve_hostname,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.repository_factory = repository_factory
        self.store = store or ProtectedNotificationSecretStore()
        self.exchange = exchange
        self.resolver = resolver
        self.clock = clock

    def send(self, delivery: ClaimedDelivery) -> DeliveryResult:
        repository = self.repository_factory()
        subscriptions = repository.subscriptions(delivery.workspace_id)
        if not subscriptions:
            return DeliveryResult("failed", "no_push_subscriptions")
        payload = push_payload(delivery.message, alert_id=delivery.alert_id, trigger_id=delivery.trigger_id)
        return self.deliver(repository, delivery.workspace_id, subscriptions, payload)

    def deliver(self, repository: NotificationSettingsRepository, workspace_id: str, subscriptions: list[StoredSubscription], payload: bytes) -> DeliveryResult:
        try:
            key = vapid_key(self.store, create=False)
        except Exception:
            logger.warning("trading_alert_vapid_key_unreadable")
            return DeliveryResult("retry", "secret_store_unavailable")
        if key is None:
            return DeliveryResult("failed", "push_not_configured")
        outcomes: list[DeliveryResult] = []
        for subscription in subscriptions:
            result = self._push(key, subscription, payload)
            if result.outcome == "delivered":
                repository.mark_delivered(subscription.subscription_id, workspace_id)
            elif result.error in ("subscription_gone",):
                repository.delete_subscription(subscription.subscription_id, workspace_id)
            outcomes.append(result)
        if any(item.outcome == "delivered" for item in outcomes):
            return DeliveryResult("delivered")
        retry = next((item for item in outcomes if item.outcome == "retry"), None)
        return retry or outcomes[-1]

    def _push(self, key: Any, subscription: StoredSubscription, payload: bytes) -> DeliveryResult:
        started = time.monotonic()
        try:
            url, hostname = _ascii_url(subscription.endpoint)
            check_outbound_url(url, strict=True, https_only=True)
            addresses = outbound_addresses(url, strict=True, resolver=bounded(self.resolver, DNS_TIMEOUT_SECONDS))
        except _Deadline:
            return DeliveryResult("retry", "dns_timeout")
        except (UnicodeError, ValueError):
            return DeliveryResult("failed", "url_policy:invalid_endpoint")
        except UrlPolicyError as exc:
            return DeliveryResult("retry", "dns_failed") if str(exc) == "hostname_resolution_failed" else DeliveryResult("failed", f"url_policy:{exc}")
        try:
            body = encrypt_push(payload, subscription.p256dh, subscription.auth)
        except ValueError:
            return DeliveryResult("failed", "subscription_gone")
        headers = {
            "Host": _host_header(url),
            "TTL": str(PUSH_TTL_SECONDS),
            "Urgency": "high",
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            "User-Agent": USER_AGENT,
            "Authorization": vapid_authorization(url, key, vapid_subject(), now=self.clock()),
        }
        for address in addresses[:3]:
            remaining = SEND_DEADLINE_SECONDS - (time.monotonic() - started)
            if remaining <= 0:
                return DeliveryResult("retry", "timeout")
            request = httpx.Request(
                "POST", _pinned_url(url, address), content=body, headers=headers,
                extensions={"timeout": httpx.Timeout(remaining).as_dict(), "sni_hostname": hostname},
            )
            try:
                response = self.exchange(request, remaining)
            except (httpx.ConnectError, httpx.ConnectTimeout):
                continue
            except httpx.HTTPError:
                return DeliveryResult("retry", "connection_failed")
            code = response.status_code
            if 200 <= code < 300:
                return DeliveryResult("delivered", status_code=code)
            if code in (404, 410):
                return DeliveryResult("failed", "subscription_gone", code)
            if code in (408, 429) or code >= 500:
                return DeliveryResult("retry", f"http_{code}", code)
            return DeliveryResult("failed", f"http_{code}", code)
        return DeliveryResult("retry", "connection_failed")


__all__ = [
    "EmailSender",
    "EmailSettings",
    "EmailSettingsWrite",
    "NotificationSettingsRepository",
    "ProtectedNotificationSecretStore",
    "PushSender",
    "PushSubscriptionWrite",
    "alert_email",
    "push_payload",
    "smtp_password_secret",
    "vapid_key",
]
