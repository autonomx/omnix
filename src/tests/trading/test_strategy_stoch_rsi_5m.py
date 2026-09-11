from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.trading.models import MarketBar
from app.trading import strategy_stoch_rsi_5m as strategy


START = datetime(2026, 9, 10, 13, 30, tzinfo=timezone.utc)  # 09:30 ET


def _bar(index: int, *, open_: str = "10", close: str = "10") -> MarketBar:
    start = START + timedelta(minutes=5 * index)
    return MarketBar(
        instrument_id="equity:NASDAQ:TEST",
        interval="5m",
        start_time=start,
        end_time=start + timedelta(minutes=5),
        open=Decimal(open_),
        high=max(Decimal(open_), Decimal(close)),
        low=min(Decimal(open_), Decimal(close)),
        close=Decimal(close),
        volume=Decimal("1000"),
        is_final=True,
        session="regular",
        provider="fixture",
        received_at=start + timedelta(minutes=5),
    )


def test_buys_on_oversold_cross_up_and_exits_on_overbought_cross_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bars = [
        _bar(0),
        _bar(1),
        _bar(2, open_="10.20"),
        _bar(3),
        _bar(4),
        _bar(5, open_="10.80"),
    ]
    monkeypatch.setattr(
        strategy,
        "_stochastic_rsi_aligned",
        lambda values, **kwargs: (
            [Decimal("5"), Decimal("9"), Decimal("50"), Decimal("97"), Decimal("96"), Decimal("96")],
            [Decimal("8"), Decimal("7"), Decimal("50"), Decimal("94"), Decimal("98"), Decimal("97")],
        ),
    )

    snapshot = strategy.evaluate_stoch_rsi_5m(bars)

    assert snapshot.state == "exited"
    assert snapshot.reason_code == "STOCH_RSI_5M_OVERBOUGHT_CROSS_DOWN"
    assert snapshot.entry_signal_time == bars[1].end_time
    assert snapshot.entry_time == bars[2].start_time
    assert snapshot.entry_price == Decimal("10.20")
    assert snapshot.exit_signal_time == bars[4].end_time
    assert snapshot.exit_time == bars[5].start_time
    assert snapshot.exit_price == Decimal("10.80")
    assert snapshot.return_pct == Decimal("0.60") / Decimal("10.20") * Decimal("100")
    assert snapshot.execution_authority is False


def test_signal_without_next_bar_is_armed_and_not_filled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bars = [_bar(0), _bar(1)]
    monkeypatch.setattr(
        strategy,
        "_stochastic_rsi_aligned",
        lambda values, **kwargs: (
            [Decimal("5"), Decimal("9")],
            [Decimal("8"), Decimal("7")],
        ),
    )

    snapshot = strategy.evaluate_stoch_rsi_5m(bars)

    assert snapshot.state == "entry_armed"
    assert snapshot.entry_signal_time == bars[1].end_time
    assert snapshot.entry_time is None
    assert snapshot.entry_price is None


def test_threshold_is_strictly_below_ten_and_above_ninety_five(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bars = [_bar(0), _bar(1)]
    monkeypatch.setattr(
        strategy,
        "_stochastic_rsi_aligned",
        lambda values, **kwargs: (
            [Decimal("5"), Decimal("10")],
            [Decimal("8"), Decimal("7")],
        ),
    )

    snapshot = strategy.evaluate_stoch_rsi_5m(bars)

    assert snapshot.state == "waiting_oversold"
    assert snapshot.reason_code == "STOCH_RSI_5M_WAITING_OVERSOLD_CROSS_UP"


def test_missing_five_minute_bar_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bars = [_bar(0), _bar(2)]
    monkeypatch.setattr(
        strategy,
        "_stochastic_rsi_aligned",
        lambda values, **kwargs: ([], []),
    )

    snapshot = strategy.evaluate_stoch_rsi_5m(bars)

    assert snapshot.state == "data_gap"
    assert snapshot.reason_code == "STOCH_RSI_5M_DATA_GAP"
    assert snapshot.data_gap_start == bars[0].end_time

