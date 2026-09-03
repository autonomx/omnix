from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

import pytest

from app.trading.models import MarketBar
from app.trading.strategies.models import GapPullbackConfig
from app.trading import strategy_stoch_trend_capture as capture


START = datetime(2026, 9, 2, 13, 36, tzinfo=timezone.utc)  # 09:36 ET


def _bar(
    index: int,
    *,
    open_: str,
    high: str,
    low: str,
    close: str,
) -> MarketBar:
    start = START + timedelta(minutes=3 * index)
    return MarketBar(
        instrument_id="equity:NASDAQ:TEST",
        interval="3m",
        start_time=start,
        end_time=start + timedelta(minutes=3),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("100000"),
        is_final=True,
        session="regular",
        provider="fixture",
        received_at=start + timedelta(minutes=3),
    )


def _patch_indicators(monkeypatch: pytest.MonkeyPatch, k_values: list[int], ema_values: list[str]) -> None:
    monkeypatch.setattr(
        capture,
        "_stochastic_rsi_aligned",
        lambda values: (
            [Decimal(str(value)) for value in k_values],
            [Decimal(str(value)) for value in k_values],
        ),
    )
    monkeypatch.setattr(
        capture,
        "_ema_aligned",
        lambda values, period: [Decimal(value) for value in ema_values],
    )


def test_range_mode_exits_full_position_at_first_overbought(monkeypatch: pytest.MonkeyPatch) -> None:
    bars = [
        _bar(0, open_="10.00", high="10.05", low="9.70", close="9.80"),
        _bar(1, open_="9.90", high="10.05", low="9.75", close="9.95"),
        _bar(2, open_="10.00", high="10.25", low="9.80", close="10.20"),
        _bar(3, open_="10.30", high="10.35", low="9.70", close="9.90"),
        _bar(4, open_="9.90", high="10.00", low="9.60", close="9.80"),
    ]
    _patch_indicators(monkeypatch, [10, 35, 90, 40, 30], ["9.8", "9.85", "9.9", "9.88", "9.86"])

    snapshot = capture.evaluate_stoch_trend_capture(bars)

    assert snapshot.state == "range_exited"
    assert snapshot.entry_price == Decimal("9.90")
    assert snapshot.runner_exit_price == Decimal("10.30")
    assert snapshot.partial_exit_price is None
    assert snapshot.return_pct is not None
    assert snapshot.return_pct > Decimal("4")


def test_trend_mode_banks_25_percent_then_holds_runner_until_break(monkeypatch: pytest.MonkeyPatch) -> None:
    bars = [
        _bar(0, open_="10.00", high="10.05", low="9.70", close="9.80"),
        _bar(1, open_="9.90", high="10.10", low="9.80", close="10.00"),
        _bar(2, open_="10.02", high="10.25", low="9.90", close="10.20"),
        _bar(3, open_="10.20", high="10.45", low="10.00", close="10.40"),
        _bar(4, open_="10.42", high="10.70", low="10.10", close="10.65"),
        _bar(5, open_="10.60", high="10.85", low="10.20", close="10.80"),
        _bar(6, open_="10.75", high="10.80", low="10.25", close="10.35"),
        _bar(7, open_="10.30", high="10.35", low="10.00", close="10.10"),
    ]
    _patch_indicators(
        monkeypatch,
        [10, 30, 45, 60, 90, 70, 55, 40],
        ["9.70", "9.75", "9.85", "9.95", "10.05", "10.15", "10.10", "10.00"],
    )

    original_break = capture._trend_break

    def fake_break(bars_, ema9_, *, entry_index: int, index: int):
        if index == 6:
            return True, Decimal("10.20")
        return False, None

    monkeypatch.setattr(capture, "_trend_break", fake_break)
    snapshot = capture.evaluate_stoch_trend_capture(bars)
    monkeypatch.setattr(capture, "_trend_break", original_break)

    assert snapshot.state == "trend_exited"
    assert snapshot.trend_confirmed_time == bars[3].end_time
    assert snapshot.first_overbought_time == bars[4].end_time
    assert snapshot.partial_exit_time == bars[5].start_time
    assert snapshot.partial_exit_price == Decimal("10.60")
    assert snapshot.partial_fraction == Decimal("0.25")
    assert snapshot.runner_exit_time == bars[7].start_time
    assert snapshot.runner_exit_price == Decimal("10.30")
    assert snapshot.combined_exit_price == Decimal("10.375")
    assert snapshot.return_pct is not None
    assert snapshot.return_pct > Decimal("4")


def test_overbought_does_not_force_full_exit_after_trend_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    bars = [
        _bar(0, open_="10.00", high="10.05", low="9.70", close="9.80"),
        _bar(1, open_="9.90", high="10.10", low="9.80", close="10.00"),
        _bar(2, open_="10.02", high="10.25", low="9.90", close="10.20"),
        _bar(3, open_="10.20", high="10.45", low="10.00", close="10.40"),
        _bar(4, open_="10.42", high="10.70", low="10.10", close="10.65"),
        _bar(5, open_="10.60", high="10.90", low="10.20", close="10.85"),
    ]
    _patch_indicators(
        monkeypatch,
        [10, 30, 45, 60, 92, 88],
        ["9.70", "9.75", "9.85", "9.95", "10.05", "10.15"],
    )
    monkeypatch.setattr(capture, "_trend_break", lambda *args, **kwargs: (False, None))

    snapshot = capture.evaluate_stoch_trend_capture(bars)

    assert snapshot.state == "trend_runner"
    assert snapshot.partial_exit_price == Decimal("10.60")
    assert snapshot.runner_exit_price is None
    assert snapshot.return_pct is None



def test_range_mode_force_flats_when_no_overbought_or_trend(monkeypatch: pytest.MonkeyPatch) -> None:
    start = datetime(2026, 9, 2, 19, 45, tzinfo=timezone.utc)  # 15:45 ET
    bars = []
    for index in range(5):
        bar_start = start + timedelta(minutes=3 * index)
        price = Decimal("10") - Decimal(index) * Decimal("0.02")
        bars.append(
            MarketBar(
                instrument_id="equity:NASDAQ:TEST",
                interval="3m",
                start_time=bar_start,
                end_time=bar_start + timedelta(minutes=3),
                open=price,
                high=price + Decimal("0.03"),
                low=price - Decimal("0.04"),
                close=price - Decimal("0.01"),
                volume=Decimal("100000"),
                is_final=True,
                session="regular",
                provider="fixture",
                received_at=bar_start + timedelta(minutes=3),
            )
        )
    _patch_indicators(
        monkeypatch,
        [10, 25, 30, 35, 40],
        ["10.2", "10.18", "10.16", "10.14", "10.12"],
    )

    snapshot = capture.evaluate_stoch_trend_capture(
        bars,
        entry_start_et=time(9, 35),
        last_entry_et=time(15, 50),
        force_flat_et=time(15, 55),
    )

    assert snapshot.state == "force_flat"
    assert snapshot.reason_code == "STOCH_TREND_RANGE_FORCE_FLAT"
    assert snapshot.entry_price == bars[1].open
    assert snapshot.runner_exit_time == bars[3].end_time
    assert snapshot.runner_exit_price == bars[3].close
    assert snapshot.runner_exit_time.astimezone(timezone.utc) > datetime(
        2026, 9, 2, 19, 55, tzinfo=timezone.utc
    )

def test_trend_force_flat_uses_post_cutoff_finalized_price(monkeypatch: pytest.MonkeyPatch) -> None:
    start = datetime(2026, 9, 2, 19, 42, tzinfo=timezone.utc)  # 15:42 ET
    bars = []
    for index in range(6):
        bar_start = start + timedelta(minutes=3 * index)
        price = Decimal("10") + Decimal(index) * Decimal("0.10")
        bars.append(
            MarketBar(
                instrument_id="equity:NASDAQ:TEST",
                interval="3m",
                start_time=bar_start,
                end_time=bar_start + timedelta(minutes=3),
                open=price,
                high=price + Decimal("0.15"),
                low=price - Decimal("0.05"),
                close=price + Decimal("0.08"),
                volume=Decimal("100000"),
                is_final=True,
                session="regular",
                provider="fixture",
                received_at=bar_start + timedelta(minutes=3),
            )
        )
    _patch_indicators(
        monkeypatch,
        [10, 30, 45, 60, 65, 70],
        ["9.80", "9.85", "9.95", "10.05", "10.15", "10.25"],
    )
    monkeypatch.setattr(
        capture,
        "_trend_confirmed",
        lambda *args, **kwargs: kwargs["index"] == 3,
    )
    monkeypatch.setattr(capture, "_trend_break", lambda *args, **kwargs: (False, None))

    snapshot = capture.evaluate_stoch_trend_capture(
        bars,
        entry_start_et=time(9, 35),
        last_entry_et=time(15, 50),
        force_flat_et=time(15, 55),
    )

    # 15:54-15:57 is the first finalized 3m bar that crosses the 15:55
    # cutoff. The replay must use its close/end, never its pre-cutoff open.
    cutoff_bar = bars[4]
    assert cutoff_bar.start_time == datetime(2026, 9, 2, 19, 54, tzinfo=timezone.utc)
    assert snapshot.state == "force_flat"
    assert snapshot.runner_exit_time == cutoff_bar.end_time
    assert snapshot.runner_exit_price == cutoff_bar.close
    assert snapshot.runner_exit_price != cutoff_bar.open


def test_risk_veto_blocks_halts_ineligible_execution_and_wide_spreads() -> None:
    decision = capture.stoch_trend_capture_risk_decision(
        {
            "halted": True,
            "execution_eligible": False,
            "spread_bps": "250",
        },
        max_spread_bps=Decimal("150"),
    )

    assert decision.allowed is False
    assert "STOCH_TREND_HALTED" in decision.reason_codes
    assert "STOCH_TREND_EXECUTION_INELIGIBLE" in decision.reason_codes
    assert "STOCH_TREND_SPREAD_TOO_WIDE" in decision.reason_codes


def test_risk_veto_allows_clean_execution_snapshot() -> None:
    decision = capture.stoch_trend_capture_risk_decision(
        {
            "halted": False,
            "execution_eligible": True,
            "spread_bps": "40",
        },
        max_spread_bps=Decimal("150"),
    )

    assert decision.allowed is True
    assert decision.reason_codes == ()


def test_trend_capture_toggle_requires_intraday_learning() -> None:
    with pytest.raises(ValueError, match="stoch trend capture requires intraday learning"):
        GapPullbackConfig(
            intraday_learning_enabled=False,
            stoch_trend_capture_enabled=True,
        )

    config = GapPullbackConfig(
        intraday_learning_enabled=True,
        stoch_trend_capture_enabled=True,
    )
    assert config.stoch_trend_capture_enabled is True
