from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.trading import strategy_stoch_rsi_5m_early_single as early_single
from app.trading.strategy_stoch_rsi_5m import StochRsi5mSnapshot, StochRsi5mTrade


def _trade(*, entry_price: str, exit_price: str, reason: str) -> StochRsi5mTrade:
    entry_time = datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc)
    exit_time = datetime(2026, 9, 10, 17, 30, tzinfo=timezone.utc)
    return StochRsi5mTrade(
        oversold_arm_time=entry_time,
        momentum_cross_time=entry_time,
        entry_signal_time=entry_time,
        entry_time=entry_time,
        entry_price=Decimal(entry_price),
        exit_signal_time=exit_time,
        exit_time=exit_time,
        exit_price=Decimal(exit_price),
        exit_reason_code=reason,
        return_pct=(Decimal(exit_price) - Decimal(entry_price))
        / Decimal(entry_price)
        * Decimal("100"),
    )


def test_early_single_keeps_only_first_completed_trade(monkeypatch) -> None:
    first = _trade(
        entry_price="10",
        exit_price="11",
        reason="STOCH_RSI_5M_CLOSE_BELOW_5_5M_EMA",
    )
    second = _trade(
        entry_price="12",
        exit_price="13",
        reason="STOCH_RSI_5M_CROSS_DOWN_BELOW_80",
    )
    snapshot = StochRsi5mSnapshot(
        state="exited",
        reason_code=second.exit_reason_code,
        trades=(first, second),
    )
    monkeypatch.setattr(
        early_single,
        "evaluate_stoch_rsi_5m",
        lambda bars, config: snapshot,
    )

    result = early_single.evaluate_stoch_rsi_5m_early_single([])

    assert result.state == "exited"
    assert result.reason_code == first.exit_reason_code
    assert result.trades == (first,)
    assert result.entry_time == first.entry_time
    assert result.exit_time == first.exit_time
    assert result.return_pct == first.return_pct


def test_early_single_passes_through_snapshot_without_trades(monkeypatch) -> None:
    snapshot = StochRsi5mSnapshot(
        state="waiting_oversold",
        reason_code="STOCH_RSI_5M_WAITING_OVERSOLD_ARM",
    )
    monkeypatch.setattr(
        early_single,
        "evaluate_stoch_rsi_5m",
        lambda bars, config: snapshot,
    )

    result = early_single.evaluate_stoch_rsi_5m_early_single([])

    assert result is snapshot
