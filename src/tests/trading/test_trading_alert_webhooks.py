"""Webhook delivery rules (TVP-0.5a): URL policy, pinning, signing, retries."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
from datetime import datetime, timezone

import httpx
import pytest

from app.apps.trading.alerts_delivery import (
    ClaimedDelivery,
    DeliveryResult,
    NotificationDeliveryMonitor,
    WebhookSender,
    retry_delay_seconds,
)
from app.security.url_policy import UrlPolicyError, check_outbound_url, outbound_addresses

HOOK = "https://hooks.example.com/services/T0/B0/token"
NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


class Store:
    def __init__(self, entries: dict[str, dict[str, str]] | None = None, *, broken: bool = False) -> None:
        self.entries = entries or {}
        self.broken = broken

    def available(self) -> bool:
        return True

    def load(self, ref: str) -> dict[str, str] | None:
        if self.broken:
            raise OSError("store unreadable")
        return self.entries.get(ref)


def public(hostname: str, port: int) -> list[str]:
    return ["93.184.216.34"]


def delivery(message: str = '{"text": "BTC up"}', ref: str | None = "ref") -> ClaimedDelivery:
    return ClaimedDelivery("d1", "t1", "a1", "webhook", message, attempt=1, max_attempts=8, webhook_ref=ref)


def sender(handler, *, entries=None, resolver=public, broken=False) -> tuple[WebhookSender, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    store = Store(entries if entries is not None else {"ref": {"url": HOOK, "secret": "s3cret"}}, broken=broken)
    return WebhookSender(store, transport=httpx.MockTransport(record), resolver=resolver, clock=lambda: NOW), seen


@pytest.fixture(autouse=True)
def no_private_networks(monkeypatch):
    monkeypatch.delenv("OMNIX_ALLOWED_PRIVATE_NETWORKS", raising=False)


def test_strict_policy_refuses_loopback_and_private_hosts_unless_configured(monkeypatch) -> None:
    for url in ("https://127.0.0.1/x", "https://10.1.2.3/x", "https://[::1]/x", "https://169.254.169.254/x"):
        with pytest.raises(UrlPolicyError):
            check_outbound_url(url, strict=True)
    with pytest.raises(UrlPolicyError, match="url_scheme_not_allowed"):
        check_outbound_url("http://hooks.example.com/x", strict=True, https_only=True)
    monkeypatch.setenv("OMNIX_ALLOWED_PRIVATE_NETWORKS", "10.1.0.0/16")
    assert check_outbound_url("https://10.1.2.3/x", strict=True) == "https://10.1.2.3/x"
    with pytest.raises(UrlPolicyError, match="loopback_address_not_allowed"):
        check_outbound_url("https://127.0.0.1/x", strict=True)
    # Non-strict callers (local model servers) keep loopback.
    assert check_outbound_url("http://127.0.0.1:1234/v1") == "http://127.0.0.1:1234/v1"


def test_a_host_with_any_internal_address_is_refused() -> None:
    assert [str(address) for address in outbound_addresses(HOOK, strict=True, resolver=public)] == ["93.184.216.34"]
    with pytest.raises(UrlPolicyError, match="private_address_not_allowed"):
        outbound_addresses(HOOK, strict=True, resolver=lambda host, port: ["93.184.216.34", "192.168.1.10"])

    def unresolvable(host: str, port: int) -> list[str]:
        raise UrlPolicyError("hostname_resolution_failed")

    with pytest.raises(UrlPolicyError, match="hostname_resolution_failed"):
        outbound_addresses(HOOK, strict=True, resolver=unresolvable)


def test_a_delivery_goes_to_the_checked_address_signed_and_typed() -> None:
    webhook, seen = sender(lambda request: httpx.Response(204))
    assert webhook.send(delivery()) == DeliveryResult("delivered", status_code=204)
    [request] = seen
    # Pinned to the address that was checked; the hostname goes in Host and TLS SNI.
    assert request.url.host == "93.184.216.34"
    assert request.url.path == "/services/T0/B0/token"
    assert request.headers["host"] == "hooks.example.com"
    assert request.extensions["sni_hostname"] == "hooks.example.com"
    assert request.headers["content-type"] == "application/json"
    assert request.headers["x-omnix-delivery"] == "d1"
    timestamp = request.headers["x-omnix-timestamp"]
    assert timestamp == str(int(NOW.timestamp()))
    expected = hmac.new(b"s3cret", f"{timestamp}.".encode() + request.content, hashlib.sha256).hexdigest()
    assert request.headers["x-omnix-signature"] == f"sha256={expected}"
    assert request.content == b'{"text": "BTC up"}'


def test_plain_messages_are_text_and_unsigned_without_a_secret() -> None:
    webhook, seen = sender(lambda request: httpx.Response(200), entries={"ref": {"url": HOOK, "secret": ""}})
    assert webhook.send(delivery("BTC crossed 100")).outcome == "delivered"
    assert seen[0].headers["content-type"] == "text/plain; charset=utf-8"
    assert "x-omnix-signature" not in seen[0].headers


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (httpx.Response(302, headers={"location": "https://127.0.0.1/"}), DeliveryResult("failed", "redirect_refused", 302)),
        (httpx.Response(404), DeliveryResult("failed", "http_404", 404)),
        (httpx.Response(500), DeliveryResult("retry", "http_500", 500)),
        (httpx.Response(429, headers={"retry-after": "120"}), DeliveryResult("retry", "http_429", 429, 120.0)),
    ],
)
def test_responses_map_to_outcomes(response, expected) -> None:
    webhook, seen = sender(lambda request: response)
    assert webhook.send(delivery()) == expected
    assert len(seen) == 1  # never follows a redirect


def test_network_errors_retry() -> None:
    def timeout(request):
        raise httpx.ConnectTimeout("slow", request=request)

    def refused(request):
        raise httpx.ConnectError("refused", request=request)

    assert sender(timeout)[0].send(delivery()) == DeliveryResult("retry", "timeout")
    assert sender(refused)[0].send(delivery()) == DeliveryResult("retry", "connection_failed")


def test_destinations_that_cannot_be_used() -> None:
    def unused(request):
        raise AssertionError("must not send")

    assert sender(unused)[0].send(delivery(ref=None)) == DeliveryResult("failed", "webhook_missing")
    assert sender(unused, entries={})[0].send(delivery()) == DeliveryResult("failed", "webhook_missing")
    # An unreadable store is not a removed webhook.
    assert sender(unused, broken=True)[0].send(delivery()) == DeliveryResult("retry", "webhook_store_unavailable")
    plain_http = {"ref": {"url": "http://hooks.example.com/x", "secret": ""}}
    assert sender(unused, entries=plain_http)[0].send(delivery()) == DeliveryResult("failed", "url_policy:url_scheme_not_allowed")
    # DNS now points the saved hostname at a private address (rebinding).
    rebound = sender(unused, resolver=lambda host, port: ["10.0.0.7"])[0]
    assert rebound.send(delivery()) == DeliveryResult("failed", "url_policy:private_address_not_allowed")

    def unresolvable(host: str, port: int) -> list[str]:
        raise UrlPolicyError("hostname_resolution_failed")

    assert sender(unused, resolver=unresolvable)[0].send(delivery()) == DeliveryResult("retry", "dns_failed")


def test_backoff_doubles_up_to_an_hour() -> None:
    assert [retry_delay_seconds(attempt) for attempt in range(1, 9)] == [30, 60, 120, 240, 480, 960, 1920, 3600]


def test_the_monitor_records_every_claimed_delivery() -> None:
    claimed = [delivery(), ClaimedDelivery("d2", "t2", "a2", "email", "hi", 1, 8, None), ClaimedDelivery("d3", "t3", "a3", "webhook", "x", 1, 8, "ref")]
    recorded: list[tuple[str, DeliveryResult]] = []

    class Repository:
        def claim_due(self, now):
            return claimed

        def record(self, item, result, now):
            recorded.append((item.delivery_id, result))
            return "delivered" if result.outcome == "delivered" else "pending"

    class Sender:
        def send(self, item):
            if item.delivery_id == "d3":
                raise RuntimeError("boom")
            return DeliveryResult("delivered", status_code=200)

    monitor = NotificationDeliveryMonitor(repository_factory=Repository, senders={"webhook": Sender()}, clock=lambda: NOW)
    assert asyncio.run(monitor.run_once()) == 1
    assert recorded == [
        ("d1", DeliveryResult("delivered", status_code=200)),
        ("d2", DeliveryResult("failed", "channel_unavailable")),
        ("d3", DeliveryResult("retry", "sender_error:RuntimeError")),
    ]
