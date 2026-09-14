from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

import pytest

from app.trading.models import MarketBar
from app.trading import strategy_leader_momentum_continuation as leader
from app.trading.strategy_timeframes import resample_final_bars


def _bar(
    start: datetime,
    *,
    interval: str = "1m",
    open_: str = "2.00",
    high: str = "2.03",
    low: str = "1.99",
    close: str = "2.02",
    volume: str = "100000",
) -> MarketBar:
    minutes = 1 if interval == "1m" else 3
    return MarketBar(
        instrument_id="equity:NASDAQ:TEST",
        interval=interval,
        start_time=start,
        end_time=start + timedelta(minutes=minutes),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal(volume),
        is_final=True,
        session="regular",
        provider="test",
    )


def _rising_one_minute_bars(count: int = 75) -> list[MarketBar]:
    start = datetime(2026, 9, 10, 13, 30, tzinfo=timezone.utc)
    bars: list[MarketBar] = []
    price = Decimal("2.00")
    for index in range(count):
        next_price = price * Decimal("1.0025")
        bars.append(
            _bar(
                start + timedelta(minutes=index),
                open_=str(price),
                high=str(next_price * Decimal("1.004")),
                low=str(price * Decimal("0.997")),
                close=str(next_price),
                volume=str(100000 + index * 2500),
            )
        )
        price = next_price
    return bars


def test_empty_tape_waits_and_never_has_execution_authority() -> None:
    snapshot = leader.evaluate_leader_momentum_continuation([])

    assert snapshot.state == "waiting_session"
    assert snapshot.reason_code == "LEADER_MOMENTUM_WAITING_SESSION"
    assert snapshot.execution_authority is False
    assert snapshot.policy_version == "leader-momentum-continuation-v1"


def test_context_rejects_invalid_negative_market_inputs() -> None:
    with pytest.raises(ValueError):
        leader.LeaderMomentumContext(tod_rvol=Decimal("-1"))
    with pytest.raises(ValueError):
        leader.LeaderMomentumContext(spread_bps=Decimal("-1"))


def test_wide_spread_reduces_deterministic_leader_score() -> None:
    bars = _rising_one_minute_bars()
    sampled = resample_final_bars(bars, "3m")
    index = len(sampled) - 1

    tight = leader._leader_score(
        bars,
        sampled,
        index=index,
        context=leader.LeaderMomentumContext(
            tod_rvol=Decimal("8"),
            relative_strength_pct=Decimal("15"),
            spread_bps=Decimal("80"),
            dollar_volume=Decimal("5000000"),
            volume_acceleration=Decimal("2"),
            hod_frequency_15m=3,
        ),
    )
    wide = leader._leader_score(
        bars,
        sampled,
        index=index,
        context=leader.LeaderMomentumContext(
            tod_rvol=Decimal("8"),
            relative_strength_pct=Decimal("15"),
            spread_bps=Decimal("300"),
            dollar_volume=Decimal("5000000"),
            volume_acceleration=Decimal("2"),
            hod_frequency_15m=3,
        ),
    )

    assert tight > wide


def test_historical_gap_is_recorded_without_invalidating_entire_session() -> None:
    bars = _rising_one_minute_bars()
    del bars[25]

    snapshot = leader.evaluate_leader_momentum_continuation(bars)

    assert snapshot.state != "data_gap"
    assert snapshot.data_gap_start is not None
    assert snapshot.data_gap_resume is not None
    assert snapshot.recovered_gap_count >= 1
    assert snapshot.execution_authority is False


def test_setup_window_must_not_cross_a_three_minute_gap() -> None:
    start = datetime(2026, 9, 10, 13, 30, tzinfo=timezone.utc)
    sampled = [
        _bar(start + timedelta(minutes=3 * index), interval="3m")
        for index in range(6)
    ]
    assert leader._is_contiguous(sampled, 0, 5) is True

    sampled[4] = _bar(start + timedelta(minutes=15), interval="3m")
    assert leader._is_contiguous(sampled, 0, 5) is False


def test_gap_through_stop_exits_at_resume_open_instead_of_fabricating_stop_fill() -> None:
    start = datetime(2026, 9, 10, 14, 0, tzinfo=timezone.utc)
    sampled = [
        _bar(start, interval="3m", open_="10", high="10.2", low="9.95", close="10.15"),
        _bar(start + timedelta(minutes=3), interval="3m", open_="10.20", high="10.35", low="10.10", close="10.30"),
        _bar(start + timedelta(minutes=6), interval="3m", open_="10.30", high="10.40", low="10.05", close="10.15"),
        # Deliberate halt/data discontinuity: next print resumes six minutes later.
        _bar(start + timedelta(minutes=12), interval="3m", open_="9.50", high="9.70", low="9.40", close="9.60"),
    ]
    ema9 = [None, Decimal("10.15"), Decimal("10.18"), Decimal("10.00")]
    atr14 = [None, Decimal("0.20"), Decimal("0.20"), Decimal("0.25")]

    trade = leader._trade_from_signal(
        sampled,
        ema9,
        atr14,
        signal_index=0,
        mode="momentum_compression",
        stop_reference=Decimal("9.90"),
        entry_atr=Decimal("0.20"),
        force_flat_et=time(15, 55),
    )

    assert trade is not None
    assert trade.entry_price == Decimal("10.20")
    assert trade.exit_reason_code == "LEADER_MOMENTUM_GAP_THROUGH_STOP"
    assert trade.exit_price == Decimal("9.50")


def test_too_wide_initial_risk_is_rejected() -> None:
    start = datetime(2026, 9, 10, 14, 0, tzinfo=timezone.utc)
    sampled = [
        _bar(start + timedelta(minutes=3 * index), interval="3m", open_="10", high="10.2", low="9.8", close="10.1")
        for index in range(5)
    ]
    ema9 = [None] * 5
    atr14 = [None] * 5

    trade = leader._trade_from_signal(
        sampled,
        ema9,
        atr14,
        signal_index=0,
        mode="controlled_pullback",
        stop_reference=Decimal("8.50"),
        entry_atr=Decimal("0.20"),
        force_flat_et=time(15, 55),
    )

    assert trade is None
