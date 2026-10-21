"""Trend continuation T1 as a daily SHADOW arm of the interday group.

The strategy monitor evaluates T1 (``strategy_trend_continuation``) on each
candidate's finalized 1m session bars once per finished bar and records
``trend_t1`` events when its state changes. When a simulated entry first
appears it also records ``trend_t1_entry``: the entry features and the live
execution quote (IBKR's NBBO while its live-data authority holds, IEX
otherwise), so real spreads and setup conditions build up as forward evidence.
T1 failed its holdouts (PREREG_TREND1, PREREG_TREND2); it has no order path.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

from .strategy_managed_finviz_shadow import INTERDAY_TRADING_STRATEGY_ID
from .strategy_monitor import StrategyRunHost
from .strategy_repository import TradingStrategyConfigDocument, TradingStrategyRepository
from .strategy_trend_continuation import evaluate_trend_t1
from .trade_logging import trade_log

TREND_T1_ARM = "trend-continuation-t1"


def trend_t1_enabled(config: TradingStrategyConfigDocument) -> bool:
    return config.strategy_id == INTERDAY_TRADING_STRATEGY_ID


def _execution_payload(execution: Any) -> dict[str, Any]:
    fields = (
        "provider", "binding_id", "bid", "ask", "bid_size", "ask_size", "last", "spread_bps",
        "source_time", "received_at", "freshness_mode", "execution_eligible", "rejection_reasons",
    )
    payload = {}
    for name in fields:
        value = getattr(execution, name, None)
        payload[name] = str(value) if isinstance(value, Decimal) else value
    for name in ("source_time", "received_at"):
        if payload.get(name) is not None and hasattr(payload[name], "isoformat"):
            payload[name] = payload[name].isoformat()
    payload["rejection_reasons"] = list(payload.get("rejection_reasons") or ())
    return payload


async def record_trend_t1(
    monitor: StrategyRunHost,
    config: TradingStrategyConfigDocument,
    strategy_repository: TradingStrategyRepository,
    market_service: Any,
    universe: Any,
    candidate: Any,
    bars: list[Any],
) -> None:
    if not trend_t1_enabled(config) or not bars:
        return
    evaluated = (config.strategy_id, candidate.instrument_id)
    if monitor.trend_t1_evaluated_through.get(evaluated) == bars[-1].end_time:
        return
    monitor.trend_t1_evaluated_through[evaluated] = bars[-1].end_time
    try:
        snapshot = evaluate_trend_t1(bars, prior_close=Decimal(str(candidate.previous_close)))
    except Exception as exc:
        trade_log(
            "auto_trading", "trend_t1_error", run_id=monitor.current_run_id, strategy_id=config.strategy_id,
            universe_id=universe.universe_id, instrument_id=candidate.instrument_id,
            error_type=type(exc).__name__, detail=str(exc), research_only=True, execution_authority=False,
        )
        return
    common = {
        "arm": TREND_T1_ARM,
        "universe_id": universe.universe_id,
        "universe_discovery_source": universe.discovery_source,
        "morning_discovery_rank": candidate.discovery_rank,
        "research_only": True,
        "execution_authority": False,
    }
    key = (config.strategy_id, candidate.instrument_id, str(snapshot.session_date))
    if snapshot.entry_time is not None and key not in monitor.trend_t1_entries_captured:
        monitor.trend_t1_entries_captured.add(key)
        try:
            execution = await asyncio.to_thread(
                market_service.execution_observation,
                candidate.instrument_id,
                candidate.binding_id,
                live_first=True,
            )
            execution_payload, execution_error = _execution_payload(execution), None
        except Exception as exc:
            execution_payload, execution_error = None, f"{type(exc).__name__}: {exc}"
        await monitor._event(
            strategy_repository,
            config,
            instrument_id=candidate.instrument_id,
            event_type="trend_t1_entry",
            state="entry_evidence",
            reason_code="TREND_T1_ENTRY_EVIDENCE",
            observed_at=snapshot.entry_time,
            payload={
                **common,
                "signal": snapshot.signal.model_dump(mode="json") if snapshot.signal else None,
                "entry_price": str(snapshot.entry_price),
                "execution": execution_payload,
                "execution_error": execution_error,
                "catalyst_evidence_count": len(getattr(candidate, "catalyst_evidence_ids", ()) or ()),
                "premarket_tod_rvol": (
                    str(candidate.tod_rvol) if getattr(candidate, "tod_rvol", None) is not None else None
                ),
                "float_shares": (
                    str(candidate.float_shares) if getattr(candidate, "float_shares", None) is not None else None
                ),
            },
        )
    marker = (snapshot.state, snapshot.reason_code)
    if monitor.trend_t1_last.get(key) == marker:
        return
    persisted = await monitor._event(
        strategy_repository,
        config,
        instrument_id=candidate.instrument_id,
        event_type="trend_t1",
        state=snapshot.state,
        reason_code=snapshot.reason_code,
        observed_at=snapshot.as_of or bars[-1].end_time,
        payload={**common, "policy": snapshot.model_dump(mode="json")},
    )
    monitor.trend_t1_last[key] = marker
    monitor.trend_t1_event_count += int(persisted)


__all__ = ["TREND_T1_ARM", "record_trend_t1", "trend_t1_enabled"]
