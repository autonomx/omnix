"""Single-trade early-session variant of the five-minute Stoch RSI strategy.

This research variant preserves the canonical evaluator and its normal entry
window, but stops accounting after the first completed trade for a symbol in a
session. It has no broker or execution authority.

Historical-gap recovery can legitimately keep prior-session trades in the
canonical evaluator's evidence tuple.  Early-single is session scoped, so it
must select the first trade whose entry belongs to the evaluator's current
session rather than blindly taking ``snapshot.trades[0]``.
"""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from .models import MarketBar
from .strategies.models import StochRsi5mConfig
from .strategy_stoch_rsi_5m import (
    StochRsi5mSnapshot,
    StochRsi5mState,
    evaluate_stoch_rsi_5m,
)


_ET = ZoneInfo("America/New_York")


def _current_session_date(
    bars: list[MarketBar] | tuple[MarketBar, ...],
    snapshot: StochRsi5mSnapshot,
) -> date | None:
    if snapshot.session_date:
        try:
            return date.fromisoformat(snapshot.session_date)
        except ValueError:
            pass
    regular = [
        bar
        for bar in bars
        if bar.is_final and bar.session == "regular"
    ]
    if not regular:
        return None
    return max(regular, key=lambda bar: bar.start_time).start_time.astimezone(_ET).date()


def _clear_prior_session_trade_metadata(
    snapshot: StochRsi5mSnapshot,
) -> StochRsi5mSnapshot:
    state: StochRsi5mState = snapshot.state
    reason_code = snapshot.reason_code
    if state in {"exited", "force_flat"}:
        state = "waiting_oversold"
        reason_code = "STOCH_RSI_5M_EARLY_SINGLE_NO_CURRENT_SESSION_TRADE"
    return snapshot.model_copy(
        update={
            "state": state,
            "reason_code": reason_code,
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
    """Evaluate canonical Stoch RSI while retaining the first current-session trade."""

    snapshot = evaluate_stoch_rsi_5m(bars, config)
    if not snapshot.trades:
        return snapshot

    session_date = _current_session_date(bars, snapshot)
    current_session_trades = tuple(
        trade
        for trade in snapshot.trades
        if session_date is not None
        and trade.entry_time.astimezone(_ET).date() == session_date
    )
    if not current_session_trades:
        return _clear_prior_session_trade_metadata(snapshot)

    first_trade = current_session_trades[0]
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
