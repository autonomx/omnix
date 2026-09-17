from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.trading import strategy_stoch_rsi_5m as strategy
from app.trading.models import MarketBar
from app.trading.strategies.models import StochRsi5mConfig


START = datetime(2026, 9, 10, 13, 30, tzinfo=timezone.utc)  # 09:30 ET
HISTORY_START = datetime(2026, 9, 9, 13, 30, tzinfo=timezone.utc)


def _bar(
    index: int,
    *,
    open_: str,
    close: str,
    high: str,
    low: str,
    volume: str = "1000",
) -> MarketBar:
    start = START + timedelta(minutes=5 * index)
    return MarketBar(
        instrument_id="equity:NASDAQ:TEST",
        interval="5m",
        start_time=start,
        end_time=start + timedelta(minutes=5),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal(volume),
        is_final=True,
        session="regular",
        provider="fixture",
        received_at=start + timedelta(minutes=5),
    )


def _with_history(signal_bars: list[MarketBar]) -> list[MarketBar]:
    history: list[MarketBar] = []
    for index in range(50):
        start = HISTORY_START + timedelta(minutes=5 * index)
        history.append(
            MarketBar(
                instrument_id="equity:NASDAQ:TEST",
                interval="5m",
                start_time=start,
                end_time=start + timedelta(minutes=5),
                open=Decimal("9.80"),
                high=Decimal("9.80"),
                low=Decimal("9.80"),
                close=Decimal("9.80"),
                volume=Decimal("1000"),
                is_final=True,
                session="regular",
                provider="fixture",
                received_at=start + timedelta(minutes=5),
            )
        )
    return [*history, *signal_bars]


def _indicator_values(
    values: list[Decimal],
    k_tail: list[str],
    d_tail: list[str],
) -> tuple[list[Decimal], list[Decimal]]:
    prefix = len(values) - len(k_tail)
    return [
        *([Decimal("50")] * prefix),
        *(Decimal(value) for value in k_tail),
    ], [
        *([Decimal("50")] * prefix),
        *(Decimal(value) for value in d_tail),
    ]


def _rising_ema(closes, period: int) -> list[Decimal]:
    values = list(closes)
    count = max(0, len(values) - period + 1)
    return [Decimal("9.80") + Decimal(index) * Decimal("0.02") for index in range(count)]


def _flat_ema(closes, period: int) -> list[Decimal]:
    values = list(closes)
    count = max(0, len(values) - period + 1)
    return [Decimal("9.90")] * count


def _signal_bars(*, breakout_volume: str = "2000", arm_low: str = "9.70") -> list[MarketBar]:
    return [
        _bar(0, open_="10.00", close="9.80", high="10.00", low=arm_low),
        _bar(1, open_="9.80", close="10.00", high="10.05", low="9.80"),
        _bar(2, open_="10.00", close="10.20", high="10.25", low="9.95"),
        # Bullish continuation, but not a confirmed break of the recovery high.
        _bar(3, open_="10.20", close="10.22", high="10.24", low="10.15"),
        # First finalized close above the recovery high.
        _bar(4, open_="10.22", close="10.50", high="10.55", low="10.20", volume=breakout_volume),
        _bar(5, open_="10.52", close="10.60", high="10.65", low="10.50"),
    ]


def _patch_signals(monkeypatch: pytest.MonkeyPatch, *, flat_ema: bool = False, vwap: str = "10.00") -> None:
    monkeypatch.setattr(
        strategy,
        "_stochastic_rsi_aligned",
        lambda values, **kwargs: _indicator_values(
            values,
            ["5", "9", "22", "30", "40", "50"],
            ["8", "7", "15", "20", "30", "40"],
        ),
    )
    monkeypatch.setattr(
        strategy,
        "exponential_moving_average",
        _flat_ema if flat_ema else _rising_ema,
    )
    monkeypatch.setattr(strategy, "session_vwap", lambda bars: Decimal(vwap))


def test_baseline_profile_remains_frozen_and_enters_before_recovery_high_break(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signal_bars = _signal_bars()
    _patch_signals(monkeypatch)

    snapshot = strategy.evaluate_stoch_rsi_5m(_with_history(signal_bars))

    assert StochRsi5mConfig().policy_profile == "baseline_v12"
    assert snapshot.policy_version == "stoch-rsi-5min-v12"
    assert snapshot.entry_time == signal_bars[3].start_time
    assert snapshot.entry_price == Decimal("10.20")


def test_guarded_profile_waits_for_high_break_and_records_entry_quality_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signal_bars = _signal_bars()
    _patch_signals(monkeypatch)
    config = StochRsi5mConfig(policy_profile="guarded_v1")

    snapshot = strategy.evaluate_stoch_rsi_5m(_with_history(signal_bars), config)

    assert snapshot.policy_version == "stoch-rsi-5min-guarded-v1"
    assert snapshot.state == "long_active"
    assert snapshot.reason_code == "STOCH_RSI_5M_GUARDED_LONG_ACTIVE"
    assert snapshot.entry_signal_time == signal_bars[2].end_time
    assert snapshot.entry_time == signal_bars[5].start_time
    assert snapshot.entry_price == Decimal("10.52")

    # The active trade is not yet in completed trades, but entry acceptance
    # proves all guarded gates were satisfied causally before this open.
    assert snapshot.trades == ()


def test_guarded_profile_rejects_weak_recovery_volume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signal_bars = _signal_bars(breakout_volume="1100")
    _patch_signals(monkeypatch)

    snapshot = strategy.evaluate_stoch_rsi_5m(
        _with_history(signal_bars),
        StochRsi5mConfig(policy_profile="guarded_v1"),
    )

    assert snapshot.state == "waiting_oversold"
    assert snapshot.reason_code == "STOCH_RSI_5M_GUARDED_FILTER_REJECTED"
    assert snapshot.entry_time is None


def test_guarded_profile_rejects_flat_or_falling_ema_regime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signal_bars = _signal_bars()
    _patch_signals(monkeypatch, flat_ema=True)

    snapshot = strategy.evaluate_stoch_rsi_5m(
        _with_history(signal_bars),
        StochRsi5mConfig(policy_profile="guarded_v1"),
    )

    assert snapshot.state == "waiting_oversold"
    assert snapshot.reason_code == "STOCH_RSI_5M_GUARDED_FILTER_REJECTED"
    assert snapshot.entry_time is None


def test_guarded_profile_rejects_breakout_below_vwap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signal_bars = _signal_bars()
    _patch_signals(monkeypatch, vwap="10.60")

    snapshot = strategy.evaluate_stoch_rsi_5m(
        _with_history(signal_bars),
        StochRsi5mConfig(policy_profile="guarded_v1"),
    )

    assert snapshot.state == "waiting_oversold"
    assert snapshot.reason_code == "STOCH_RSI_5M_GUARDED_FILTER_REJECTED"
    assert snapshot.entry_time is None


def test_guarded_profile_rejects_setup_with_excessive_structural_risk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signal_bars = _signal_bars(arm_low="9.50")
    _patch_signals(monkeypatch)

    snapshot = strategy.evaluate_stoch_rsi_5m(
        _with_history(signal_bars),
        StochRsi5mConfig(policy_profile="guarded_v1"),
    )

    assert snapshot.state == "waiting_oversold"
    assert snapshot.reason_code == "STOCH_RSI_5M_GUARDED_FILTER_REJECTED"
    assert snapshot.entry_time is None
