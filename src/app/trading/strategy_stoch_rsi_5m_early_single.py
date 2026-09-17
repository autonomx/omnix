"""Single-trade early-session variant of the five-minute Stoch RSI strategy.

This research variant preserves the canonical evaluator and its normal entry
window, but stops accounting after the first completed trade for a symbol in a
session. It has no broker or execution authority.
"""

from __future__ import annotations

from .models import MarketBar
from .strategies.models import StochRsi5mConfig
from .strategy_stoch_rsi_5m import (
    StochRsi5mSnapshot,
    StochRsi5mState,
    evaluate_stoch_rsi_5m,
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


__all__ = ["evaluate_stoch_rsi_5m_early_single"]
