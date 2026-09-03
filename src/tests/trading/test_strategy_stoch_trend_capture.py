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


def test_extended_hours_bars_do_not_enter_indicator_warmup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prior = MarketBar(
        instrument_id="equity:NASDAQ:TEST",
        interval="3m",
        start_time=datetime(2026, 9, 1, 19, 57, tzinfo=timezone.utc),
        end_time=datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc),
        open=Decimal("10"),
        high=Decimal("10.05"),
        low=Decimal("9.95"),
        close=Decimal("10"),
        volume=Decimal("100000"),
        is_final=True,
        session="regular",
        provider="fixture",
        received_at=datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc),
    )
    current = _bar(0, open_="9.90", high="10.00", low="9.70", close="9.80")
    extended = MarketBar(
        instrument_id="equity:NASDAQ:TEST",
        interval="3m",
        start_time=datetime(2026, 9, 2, 20, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 9, 2, 20, 3, tzinfo=timezone.utc),
        open=Decimal("20"),
        high=Decimal("21"),
        low=Decimal("19"),
        close=Decimal("20"),
        volume=Decimal("100000"),
        is_final=True,
        session="extended_post",
        provider="fixture",
        received_at=datetime(2026, 9, 2, 20, 3, tzinfo=timezone.utc),
    )
    seen: list[Decimal] = []

    def fake_stoch(values):
        seen[:] = values
        return (
            [Decimal("50"), Decimal("10")],
            [Decimal("50"), Decimal("10")],
        )

    monkeypatch.setattr(capture, "_stochastic_rsi_aligned", fake_stoch)

    snapshot = capture.evaluate_stoch_trend_capture([prior, current, extended])

    assert seen == [prior.close, current.close]
    assert extended.close not in seen
    assert snapshot.state == "entry_armed"
    assert snapshot.entry_signal_time == current.end_time


def test_prior_session_bars_warm_early_regular_session_stoch_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prior_start = datetime(2026, 9, 1, 18, 0, tzinfo=timezone.utc)  # 14:00 ET
    prior = []
    for index in range(32):
        start = prior_start + timedelta(minutes=3 * index)
        prior.append(
            MarketBar(
                instrument_id="equity:NASDAQ:TEST",
                interval="3m",
                start_time=start,
                end_time=start + timedelta(minutes=3),
                open=Decimal("10"),
                high=Decimal("10.10"),
                low=Decimal("9.90"),
                close=Decimal("10"),
                volume=Decimal("100000"),
                is_final=True,
                session="regular",
                provider="fixture",
                received_at=start + timedelta(minutes=3),
            )
        )

    current_open_start = datetime(2026, 9, 2, 13, 30, tzinfo=timezone.utc)  # 09:30 ET
    current_open = MarketBar(
        instrument_id="equity:NASDAQ:TEST",
        interval="3m",
        start_time=current_open_start,
        end_time=current_open_start + timedelta(minutes=3),
        open=Decimal("10.00"),
        high=Decimal("10.05"),
        low=Decimal("9.85"),
        close=Decimal("9.95"),
        volume=Decimal("100000"),
        is_final=True,
        session="regular",
        provider="fixture",
        received_at=current_open_start + timedelta(minutes=3),
    )
    current_start = datetime(2026, 9, 2, 13, 33, tzinfo=timezone.utc)  # 09:33 ET
    current = MarketBar(
        instrument_id="equity:NASDAQ:TEST",
        interval="3m",
        start_time=current_start,
        end_time=current_start + timedelta(minutes=3),
        open=Decimal("9.90"),
        high=Decimal("10"),
        low=Decimal("9.70"),
        close=Decimal("9.80"),
        volume=Decimal("100000"),
        is_final=True,
        session="regular",
        provider="fixture",
        received_at=current_start + timedelta(minutes=3),
    )

    def fake_stoch(values):
        k = [None] * len(values)
        d = [None] * len(values)
        # Make the prior-session tail oversold too; signal selection must ignore
        # it. The 09:30-09:33 bar is neutral and the latest 09:33-09:36 bar arms.
        k[-3] = Decimal("10")
        d[-3] = Decimal("10")
        k[-2] = Decimal("50")
        d[-2] = Decimal("50")
        k[-1] = Decimal("12")
        d[-1] = Decimal("14")
        return k, d

    monkeypatch.setattr(capture, "_stochastic_rsi_aligned", fake_stoch)

    snapshot = capture.evaluate_stoch_trend_capture([*prior, current_open, current])

    assert snapshot.state == "entry_armed"
    assert snapshot.entry_signal_time == current.end_time
    assert snapshot.as_of == current.end_time
    assert snapshot.entry_signal_time.astimezone(capture._ET).time() == time(9, 36)
    assert snapshot.stochastic_rsi_k == Decimal("12")
    assert snapshot.stochastic_rsi_d == Decimal("14")


def test_incomplete_opening_bucket_does_not_fall_back_to_prior_session() -> None:
    prior_start = datetime(2026, 9, 1, 19, 54, tzinfo=timezone.utc)  # 15:54 ET
    bars = []
    for index in range(3):
        start = prior_start + timedelta(minutes=index)
        bars.append(
            MarketBar(
                instrument_id="equity:NASDAQ:TEST",
                interval="1m",
                start_time=start,
                end_time=start + timedelta(minutes=1),
                open=Decimal("10"),
                high=Decimal("10.05"),
                low=Decimal("9.95"),
                close=Decimal("10"),
                volume=Decimal("10000"),
                is_final=True,
                session="regular",
                provider="fixture",
                received_at=start + timedelta(minutes=1),
            )
        )

    current_start = datetime(2026, 9, 2, 13, 30, tzinfo=timezone.utc)  # 09:30 ET
    bars.append(
        MarketBar(
            instrument_id="equity:NASDAQ:TEST",
            interval="1m",
            start_time=current_start,
            end_time=current_start + timedelta(minutes=1),
            open=Decimal("10"),
            high=Decimal("10.05"),
            low=Decimal("9.95"),
            close=Decimal("10"),
            volume=Decimal("10000"),
            is_final=True,
            session="regular",
            provider="fixture",
            received_at=current_start + timedelta(minutes=1),
        )
    )

    snapshot = capture.evaluate_stoch_trend_capture(bars)

    assert snapshot.state == "waiting_oversold"
    assert snapshot.reason_code == "STOCH_TREND_WAITING_FOR_REGULAR_SESSION"
    assert snapshot.as_of is None
    assert snapshot.entry_signal_time is None


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


def test_missing_current_session_opening_bucket_invalidates_raw_minute_replay() -> None:
    bars = []
    start = datetime(2026, 9, 2, 13, 33, tzinfo=timezone.utc)  # first raw bar is 09:33 ET
    for index in range(6):
        bar_start = start + timedelta(minutes=index)
        bars.append(
            MarketBar(
                instrument_id="equity:NASDAQ:TEST",
                interval="1m",
                start_time=bar_start,
                end_time=bar_start + timedelta(minutes=1),
                open=Decimal("10"),
                high=Decimal("10.05"),
                low=Decimal("9.95"),
                close=Decimal("10"),
                volume=Decimal("10000"),
                is_final=True,
                session="regular",
                provider="fixture",
                received_at=bar_start + timedelta(minutes=1),
            )
        )

    snapshot = capture.evaluate_stoch_trend_capture(bars)

    assert snapshot.state == "data_gap"
    assert snapshot.reason_code == "STOCH_TREND_REGULAR_SESSION_DATA_GAP"
    assert snapshot.data_gap_start_time == datetime(
        2026, 9, 2, 13, 30, tzinfo=timezone.utc
    )
    assert snapshot.data_gap_resume_time == datetime(
        2026, 9, 2, 13, 33, tzinfo=timezone.utc
    )
    assert snapshot.return_pct is None


def test_internal_three_minute_gap_invalidates_shadow_replay() -> None:
    bars = [
        _bar(0, open_="10.00", high="10.05", low="9.70", close="9.80"),
        _bar(1, open_="9.90", high="10.05", low="9.75", close="9.95"),
        # Skip index 2 entirely to simulate a halt or missing source bucket.
        _bar(3, open_="10.30", high="10.35", low="10.00", close="10.20"),
    ]

    snapshot = capture.evaluate_stoch_trend_capture(bars)

    assert snapshot.state == "data_gap"
    assert snapshot.reason_code == "STOCH_TREND_REGULAR_SESSION_DATA_GAP"
    assert snapshot.data_gap_start_time == bars[1].end_time
    assert snapshot.data_gap_resume_time == bars[2].start_time
    assert snapshot.return_pct is None


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
