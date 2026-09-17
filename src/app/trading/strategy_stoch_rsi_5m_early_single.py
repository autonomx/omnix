"""Single-trade early-session variant of the five-minute Stoch RSI strategy.

This research variant preserves the canonical evaluator and its normal entry
window, but stops accounting after the first completed trade for a symbol in a
session. It has no broker or execution authority.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from .models import MarketBar
from .strategies.models import StochRsi5mConfig
from .strategy_stoch_rsi_5m import (
    StochRsi5mSnapshot,
    StochRsi5mState,
    evaluate_stoch_rsi_5m,
)
from .strategy_timeframes import resample_final_bars


PRE_ENTRY_RANGE_CAP_PCT = Decimal("150")
_ET = ZoneInfo("America/New_York")


def _completed_pre_entry_bars(
    bars: list[MarketBar] | tuple[MarketBar, ...],
    *,
    entry_time: datetime,
) -> list[MarketBar]:
    session_date = entry_time.astimezone(_ET).date()
    return sorted(
        (
            bar
            for bar in bars
            if bar.is_final
            and bar.session == "regular"
            and bar.start_time.astimezone(_ET).date() == session_date
            and bar.end_time <= entry_time
        ),
        key=lambda bar: bar.start_time,
    )


def _reject_pre_entry_range(
    snapshot: StochRsi5mSnapshot,
    *,
    entry_time: datetime,
    completed_bar_count: int,
) -> StochRsi5mSnapshot:
    return snapshot.model_copy(
        update={
            "state": "waiting_oversold",
            "reason_code": "STOCH_RSI_5M_EARLY_SINGLE_PRE_ENTRY_RANGE_ABOVE_150",
            "as_of": entry_time,
            "five_minute_bar_count": completed_bar_count,
            "ema_50_5m": None,
            "stochastic_rsi_k": None,
            "stochastic_rsi_d": None,
            "previous_stochastic_rsi_k": None,
            "previous_stochastic_rsi_d": None,
            "oversold_arm_time": None,
            "momentum_cross_time": None,
            "entry_signal_time": None,
            "entry_time": None,
            "entry_price": None,
            "exit_signal_time": None,
            "exit_time": None,
            "exit_price": None,
            "return_pct": None,
            "trades": (),
        }
    )


def evaluate_stoch_rsi_5m_early_single(
    bars: list[MarketBar] | tuple[MarketBar, ...],
    config: StochRsi5mConfig | None = None,
) -> StochRsi5mSnapshot:
    """Evaluate canonical Stoch RSI while retaining only the first trade."""

    snapshot = evaluate_stoch_rsi_5m(bars, config)
    if not snapshot.trades:
        return snapshot

    first_trade = snapshot.trades[0]
    pre_entry_bars = _completed_pre_entry_bars(
        bars,
        entry_time=first_trade.entry_time,
    )
    if pre_entry_bars:
        pre_entry_high = max(bar.high for bar in pre_entry_bars)
        pre_entry_low = min(bar.low for bar in pre_entry_bars)
        pre_entry_range_pct = (
            (pre_entry_high / pre_entry_low - Decimal("1")) * Decimal("100")
            if pre_entry_low > 0
            else Decimal("Infinity")
        )
        if pre_entry_range_pct > PRE_ENTRY_RANGE_CAP_PCT:
            source_interval = pre_entry_bars[0].interval
            completed_bar_count = (
                len(pre_entry_bars)
                if source_interval == "5m"
                else len(resample_final_bars(pre_entry_bars, "5m"))
            )
            return _reject_pre_entry_range(
                snapshot,
                entry_time=first_trade.entry_time,
                completed_bar_count=completed_bar_count,
            )

    state: StochRsi5mState = (
        "force_flat"
        if first_trade.exit_reason_code == "STOCH_RSI_5M_FORCE_FLAT"
        else "exited"
    )
    return snapshot.model_copy(
        update={
            "state": state,
            "reason_code": first_trade.exit_reason_code,
            "oversold_arm_time": first_trade.oversold_arm_time,
            "momentum_cross_time": first_trade.momentum_cross_time,
            "entry_signal_time": first_trade.entry_signal_time,
            "entry_time": first_trade.entry_time,
            "entry_price": first_trade.entry_price,
            "exit_signal_time": first_trade.exit_signal_time,
            "exit_time": first_trade.exit_time,
            "exit_price": first_trade.exit_price,
            "return_pct": first_trade.return_pct,
            "trades": (first_trade,),
        }
    )


__all__ = [
    "PRE_ENTRY_RANGE_CAP_PCT",
    "evaluate_stoch_rsi_5m_early_single",
]
