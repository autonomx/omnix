from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.trading.cache import TradingMarketDataCache
from app.trading.providers.additional_crypto import AdditionalCryptoProvider
from app.trading.providers.bar_semantics import (
    continuous_bar_end,
    equity_bar_times,
    is_final_bar,
)
from app.trading.providers.http_runtime import ProviderHttpRuntime


class FakeResponse:
    def __init__(self, payload, *, status_code: int = 200, text: str = "") -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers: dict[str, str] = {}
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls = 0

    def request(self, method: str, url: str, **kwargs):
        self.calls += 1
        return self.responses.pop(0)


def test_interval_and_equity_session_semantics_are_explicit() -> None:
    start = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)
    assert continuous_bar_end(start, "2h") == start + timedelta(hours=2)
    regular_start, regular_end, session = equity_bar_times(
        datetime(2026, 8, 6, 13, 30, tzinfo=timezone.utc),
        "1d",
        "America/New_York",
    )
    assert session == "regular"
    assert regular_start < regular_end
    assert regular_end.hour in {20, 21}
    assert is_final_bar(regular_end, regular_end + timedelta(seconds=1)) is True
    assert is_final_bar(regular_end, regular_end - timedelta(seconds=1)) is False


def test_additional_crypto_latest_open_candle_is_not_marked_final() -> None:
    future = datetime.now(timezone.utc) + timedelta(minutes=10)
    timestamp = int(future.timestamp())
    session = FakeSession(
        [FakeResponse([[timestamp, "99", "101", "100", "100.5", "10"]])]
    )
    runtime = ProviderHttpRuntime(
        "coinbase",
        session=session,
        max_attempts=1,
        initial_backoff_seconds=0,
    )
    provider = AdditionalCryptoProvider("coinbase", runtime=runtime)
    response = provider.get_bars("crypto:COINBASE:spot:BTC-USD", "1m", 1)
    assert response.bars[0].end_time > response.bars[0].start_time
    assert response.bars[0].is_final is False


def test_provider_runtime_retries_and_reports_health() -> None:
    session = FakeSession([FakeResponse({}, status_code=503), FakeResponse({"ok": True})])
    runtime = ProviderHttpRuntime(
        "fixture",
        session=session,
        max_attempts=2,
        initial_backoff_seconds=0,
    )
    response = runtime.get("https://example.invalid", timeout=1)
    assert response.json() == {"ok": True}
    snapshot = runtime.snapshot()
    assert session.calls == 2
    assert snapshot.success_count == 1
    assert snapshot.failure_count == 1
    assert snapshot.status == "ready"


def test_disk_cache_is_atomic_bounded_and_rejects_corruption(tmp_path: Path) -> None:
    cache = TradingMarketDataCache(max_entries=2, cache_dir=tmp_path)
    cache.put("one", {"value": 1}, ttl_seconds=60, source="fixture")
    cache.put("two", {"value": 2}, ttl_seconds=60, source="fixture")
    cache.put("three", {"value": 3}, ttl_seconds=60, source="fixture")
    assert len(list(tmp_path.glob("*.json"))) <= 2
    assert not list(tmp_path.glob("*.tmp"))

    path = cache._disk_path("three")
    assert path is not None and path.exists()
    path.write_text(json.dumps({"key": "three", "value": {"value": 999}, "expires_at": 9999999999, "source": "fixture", "fingerprint": "bad"}), encoding="utf-8")
    cache._entries.clear()
    assert cache.get("three") is None
    assert not path.exists()
