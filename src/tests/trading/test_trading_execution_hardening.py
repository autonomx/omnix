from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.trading.gapper_dataset import GapperCandidate, freeze_gapper_universe
from app.trading.paper import (
    PaperExecutionPolicy,
    PaperMarketObservation,
    PaperOrder,
    paper_fill_decision,
    paper_protection_trigger,
)
from app.trading.providers.alpaca_iex_status import AlpacaIexStatusCache, AlpacaTradingStatus
from app.trading.us_equity_calendar import us_equity_session


NOW = datetime(2026, 8, 18, 14, 0, tzinfo=timezone.utc)


def _order(*, side: str = "buy", quantity: str = "1000") -> PaperOrder:
    return PaperOrder(
        account_id="paper",
        order_id=f"order-{side}",
        instrument_id="equity:NASDAQ:TEST",
        binding_id="yahoo:historical_polling:equity:NASDAQ:TEST",
        side=side,
        order_type="market",
        quantity=Decimal(quantity),
        idempotency_key=f"idem-{side}",
    )


def _observation(**overrides) -> PaperMarketObservation:
    payload = {
        "instrument_id": "equity:NASDAQ:TEST",
        "binding_id": "yahoo:historical_polling:equity:NASDAQ:TEST",
        "provider": "alpaca_iex",
        "price": Decimal("10"),
        "bid": Decimal("9.99"),
        "ask": Decimal("10.01"),
        "bid_size": Decimal("200"),
        "ask_size": Decimal("300"),
        "high": Decimal("10.2"),
        "low": Decimal("9.8"),
        "volume": Decimal("1000000"),
        "bar_start_time": NOW,
        "source_time": NOW,
        "evaluated_at": NOW,
        "execution_eligible": True,
        "freshness_mode": "live",
        "halted": False,
    }
    payload.update(overrides)
    return PaperMarketObservation(**payload)


def test_live_fill_capacity_prefers_displayed_book_over_large_bar_or_daily_volume() -> None:
    policy = PaperExecutionPolicy(max_volume_participation_pct=Decimal("0.10"), latency_ms=0)
    buy = paper_fill_decision(_order(side="buy"), _observation(), policy)
    sell = paper_fill_decision(_order(side="sell"), _observation(), policy)

    # 10% of ask/bid displayed size, not 10% of the million-share volume field.
    assert buy.fill_quantity == Decimal("30")
    assert sell.fill_quantity == Decimal("20")


def test_historical_fill_capacity_uses_bar_volume_when_no_book_size_exists() -> None:
    policy = PaperExecutionPolicy(max_volume_participation_pct=Decimal("0.10"), latency_ms=0)
    historical = _observation(
        provider="backtest:yahoo",
        bid_size=None,
        ask_size=None,
        volume=Decimal("500"),
        freshness_mode="historical",
    )
    decision = paper_fill_decision(_order(), historical, policy)
    assert decision.fill_quantity == Decimal("50")


def test_protection_trigger_is_stop_first_and_activation_safe() -> None:
    ambiguous = _observation(high=Decimal("12"), low=Decimal("8"))
    assert paper_protection_trigger(
        is_long=True,
        stop_price=Decimal("9"),
        target_price=Decimal("11"),
        observation=ambiguous,
        activated_at=NOW,
    ) == "stop"

    # A minute range that began before the fill cannot prove that its old low was
    # touched after entry. Only the current executable price is trusted then.
    pre_entry_range = _observation(
        price=Decimal("10.5"),
        high=Decimal("11.5"),
        low=Decimal("8.5"),
        bar_start_time=NOW - timedelta(minutes=1),
    )
    assert paper_protection_trigger(
        is_long=True,
        stop_price=Decimal("9"),
        target_price=Decimal("11"),
        observation=pre_entry_range,
        activated_at=NOW,
    ) is None


def test_status_cache_keeps_known_halt_fail_closed_across_disconnect() -> None:
    cache = AlpacaIexStatusCache()
    cache.set_connected(True)
    cache.record(
        AlpacaTradingStatus(
            symbol="TEST",
            status_code="H",
            reason_code="T1",
            message="halt",
            observed_at=NOW,
            halted=True,
        )
    )
    assert cache.halted("TEST") is True
    cache.set_connected(False)
    assert cache.halted("TEST") is True

    cache.record(
        AlpacaTradingStatus(
            symbol="TEST",
            status_code="Q",
            reason_code=None,
            message="resume",
            observed_at=NOW + timedelta(minutes=1),
            halted=False,
        )
    )
    # Resume evidence is no longer authoritative after disconnect; a later halt
    # could have been missed while the status stream was unavailable.
    assert cache.halted("TEST") is None


def test_us_equity_calendar_rejects_holidays_and_handles_early_close() -> None:
    # Christmas 2026 is Friday; regular session must be closed.
    christmas = datetime(2026, 12, 25, 15, 0, tzinfo=timezone.utc)
    assert us_equity_session(christmas) == "closed"

    # Day after Thanksgiving closes at 13:00 ET. Extended trading remains open
    # at 13:30 ET but is closed after the standard 17:00 ET early-session cutoff.
    after_thanksgiving = datetime(2026, 11, 27, 18, 30, tzinfo=timezone.utc)
    assert us_equity_session(after_thanksgiving) == "extended_post"
    after_early_extended_close = datetime(2026, 11, 27, 22, 30, tzinfo=timezone.utc)
    assert us_equity_session(after_early_extended_close) == "closed"


def test_provider_universe_requires_point_in_time_candidate_evidence() -> None:
    candidate = GapperCandidate(
        instrument_id="equity:NASDAQ:TEST",
        binding_id="yahoo:historical_polling:equity:NASDAQ:TEST",
        observed_at=NOW + timedelta(seconds=1),
        previous_close=Decimal("8"),
        premarket_price=Decimal("10"),
        gap_pct=Decimal("25"),
        premarket_volume=Decimal("100000"),
        premarket_dollar_volume=Decimal("1000000"),
        tod_rvol=Decimal("3"),
        discovery_rank=1,
    )
    with pytest.raises(ValueError, match="after universe freeze"):
        freeze_gapper_universe(
            universe_id="future-evidence",
            session_date=date(2026, 8, 18),
            evaluation_time=NOW,
            discovery_source="provider",
            candidates=[candidate],
        )

    missing_timestamp = candidate.model_copy(update={"observed_at": None})
    with pytest.raises(ValueError, match="requires observed_at"):
        freeze_gapper_universe(
            universe_id="missing-evidence",
            session_date=date(2026, 8, 18),
            evaluation_time=NOW,
            discovery_source="provider",
            candidates=[missing_timestamp],
        )
