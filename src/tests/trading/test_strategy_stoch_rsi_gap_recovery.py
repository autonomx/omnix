from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.trading.models import MarketBar
from app.trading import strategy_stoch_rsi_5m as strategy


OPEN = datetime(2026, 9, 16, 13, 30, tzinfo=timezone.utc)  # 09:30 ET


def _bar(index: int) -> MarketBar:
    start = OPEN + timedelta(minutes=5 * index)
    open_price = Decimal("10") + Decimal(index) * Decimal("0.01")
    close = open_price + Decimal("0.05")
    return MarketBar(
        instrument_id="equity:NASDAQ:TEST",
        interval="5m",
        start_time=start,
        end_time=start + timedelta(minutes=5),
        open=open_price,
        high=close + Decimal("0.02"),
        low=open_price - Decimal("0.02"),
        close=close,
        volume=Decimal("1000"),
        is_final=True,
        session="regular",
        provider="fixture",
        received_at=start + timedelta(minutes=5),
    )


def _flat_indicators(values, **_kwargs):
    count = len(list(values))
    return [Decimal("50")] * count, [Decimal("50")] * count


def test_old_gap_resumes_after_fifty_clean_five_minute_bars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 09:30-09:55, then an unrecoverable 20-minute hole, then 50 clean 5m bars.
    bars = [_bar(index) for index in range(6)]
    bars += [_bar(index) for index in range(10, 60)]
    monkeypatch.setattr(strategy, "_stochastic_rsi_aligned", _flat_indicators)

    snapshot = strategy.evaluate_stoch_rsi_5m(bars)

    assert snapshot.state != "data_gap"
    assert snapshot.reason_code == "STOCH_RSI_5M_WAITING_OVERSOLD_ARM"
    assert snapshot.five_minute_bar_count == 50
    assert snapshot.data_gap_start == _bar(6).start_time
    assert snapshot.data_gap_resume == _bar(10).start_time
    assert snapshot.execution_authority is False


def test_old_gap_remains_blocked_until_post_gap_warmup_is_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bars = [_bar(index) for index in range(6)]
    bars += [_bar(index) for index in range(10, 59)]  # 49 clean bars
    monkeypatch.setattr(strategy, "_stochastic_rsi_aligned", _flat_indicators)

    snapshot = strategy.evaluate_stoch_rsi_5m(bars)

    assert snapshot.state == "data_gap"
    assert snapshot.reason_code == "STOCH_RSI_5M_POST_GAP_WARMUP"
    assert snapshot.five_minute_bar_count == 49
    assert snapshot.data_gap_resume == _bar(10).start_time


def test_open_position_spanning_gap_never_gets_reset_into_a_new_trade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The prefix has enough history to enter immediately before the gap and no
    # deterministic exit. The missing interval could contain the true exit, so
    # post-gap data must not erase that uncertainty.
    bars = [_bar(index) for index in range(55)]
    bars += [_bar(index) for index in range(56, 61)]

    def active_trade_indicators(values, **_kwargs):
        count = len(list(values))
        k = [Decimal("50")] * count
        d = [Decimal("40")] * count
        if count >= 55:
            k[49], d[49] = Decimal("5"), Decimal("8")
            k[50], d[50] = Decimal("9"), Decimal("7")
            k[51], d[51] = Decimal("22"), Decimal("15")
            k[52], d[52] = Decimal("40"), Decimal("30")
        return k, d

    monkeypatch.setattr(strategy, "_stochastic_rsi_aligned", active_trade_indicators)

    snapshot = strategy.evaluate_stoch_rsi_5m(bars)

    assert snapshot.state == "data_gap"
    assert snapshot.reason_code == "STOCH_RSI_5M_OPEN_POSITION_SPANS_GAP"
    assert snapshot.data_gap_start == _bar(55).start_time
    assert snapshot.data_gap_resume == _bar(56).start_time
