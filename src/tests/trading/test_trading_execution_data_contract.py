from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.trading.execution import (
    ExecutionEligibilityPolicy,
    ExecutionObservation,
    assess_execution_observation,
    execution_observation_from_quote,
)


NOW = datetime(2026, 8, 18, 14, 0, tzinfo=timezone.utc)


def observation(**overrides) -> ExecutionObservation:
    payload = {
        "instrument_id": "equity:NASDAQ:TEST",
        "binding_id": "yahoo:historical_polling:equity:NASDAQ:TEST",
        "provider": "fixture",
        "bid": Decimal("9.99"),
        "ask": Decimal("10.01"),
        "last": Decimal("10"),
        "cumulative_volume": Decimal("1000000"),
        "source_time": NOW - timedelta(milliseconds=200),
        "received_at": NOW,
        "session": "regular",
        "freshness_mode": "polled",
    }
    payload.update(overrides)
    return ExecutionObservation(**payload)


def test_execution_observation_is_fail_closed_and_spread_aware() -> None:
    policy = ExecutionEligibilityPolicy(max_age_seconds="2", max_spread_bps="100")
    good = assess_execution_observation(observation(), policy)
    assert good.execution_eligible is True
    assert good.rejection_reasons == ()
    assert good.spread_bps is not None

    stale = assess_execution_observation(
        observation(source_time=NOW - timedelta(seconds=10)),
        policy,
    )
    assert stale.execution_eligible is False
    assert "STALE_MARKET_DATA" in stale.rejection_reasons

    no_book = assess_execution_observation(observation(bid=None, ask=None), policy)
    assert no_book.execution_eligible is False
    assert "BID_ASK_UNAVAILABLE" in no_book.rejection_reasons

    wide = assess_execution_observation(
        observation(bid=Decimal("9"), ask=Decimal("11")),
        policy,
    )
    assert wide.execution_eligible is False
    assert "SPREAD_TOO_WIDE" in wide.rejection_reasons


def test_cached_or_unknown_prices_can_never_be_execution_eligible() -> None:
    cached = assess_execution_observation(observation(freshness_mode="cached"))
    assert cached.execution_eligible is False
    assert "NON_EXECUTION_FRESHNESS" in cached.rejection_reasons

    closed = assess_execution_observation(observation(session="closed"))
    assert closed.execution_eligible is False
    assert "SESSION_NOT_EXECUTABLE" in closed.rejection_reasons


def test_provider_quote_normalization_preserves_source_time_and_book() -> None:
    quote = {
        "instrument_id": "equity:NASDAQ:TEST",
        "binding_id": "binding",
        "provider": "fixture",
        "bid": "1.99",
        "ask": "2.01",
        "last": "2.00",
        "cumulative_volume": "500000",
        "source_time": (NOW - timedelta(milliseconds=50)).isoformat(),
        "session": "extended_pre",
        "freshness_mode": "polled",
    }
    value = execution_observation_from_quote(
        quote,
        binding_id="binding",
        provider="fixture",
        received_at=NOW,
    )
    assert value.bid == Decimal("1.99")
    assert value.ask == Decimal("2.01")
    assert value.last == Decimal("2.00")
    assert value.session == "extended_pre"
    assert value.age_seconds == Decimal("0.05")
