"""Leader Momentum v1.2 as a daily SHADOW arm of the interday group.

``leader-momentum-continuation`` is one of the interday group's embedded arms.
The strategy monitor evaluates it on each candidate's finalized 1m session bars
once per finished bar, beside the other arms, and records ``leader_momentum``
events: the snapshot when its state, reason or completed trades change, not on
every minute. Entries are allowed 09:35-15:00 ET, the window PREREG_TREND1
tested (it failed that holdout; it runs here as forward evidence). Research
evidence only: nothing here places orders or carries execution authority.
"""
from __future__ import annotations

from datetime import time
from typing import Any

from .strategy_leader_momentum_continuation import evaluate_leader_momentum_continuation
from .strategy_managed_finviz_shadow import INTERDAY_TRADING_STRATEGY_ID
from .strategy_monitor import StrategyRunHost
from .strategy_repository import TradingStrategyConfigDocument, TradingStrategyRepository
from .trade_logging import trade_log

LEADER_MOMENTUM_ARM = "leader-momentum-continuation"
LEADER_MOMENTUM_ENTRY_START_ET = time(9, 35)
LEADER_MOMENTUM_LAST_ENTRY_ET = time(15, 0)


def leader_momentum_enabled(config: TradingStrategyConfigDocument) -> bool:
    return config.strategy_id == INTERDAY_TRADING_STRATEGY_ID


async def record_leader_momentum(
    monitor: StrategyRunHost,
    config: TradingStrategyConfigDocument,
    strategy_repository: TradingStrategyRepository,
    universe: Any,
    candidate: Any,
    bars: list[Any],
) -> None:
    if not leader_momentum_enabled(config) or not bars:
        return
    # The policy replays the whole session, so evaluate once per finished bar.
    evaluated = (config.strategy_id, candidate.instrument_id)
    if monitor.leader_momentum_evaluated_through.get(evaluated) == bars[-1].end_time:
        return
    monitor.leader_momentum_evaluated_through[evaluated] = bars[-1].end_time
    try:
        snapshot = evaluate_leader_momentum_continuation(
            bars,
            entry_start_et=LEADER_MOMENTUM_ENTRY_START_ET,
            last_entry_et=LEADER_MOMENTUM_LAST_ENTRY_ET,
            force_flat_et=config.risk.force_flat_et,
        )
    except Exception as exc:
        trade_log(
            "auto_trading",
            "leader_momentum_error",
            run_id=monitor.current_run_id,
            strategy_id=config.strategy_id,
            universe_id=universe.universe_id,
            instrument_id=candidate.instrument_id,
            error_type=type(exc).__name__,
            detail=str(exc),
            research_only=True,
            execution_authority=False,
        )
        return
    key = (config.strategy_id, candidate.instrument_id, str(snapshot.session_date))
    marker = (snapshot.state, snapshot.reason_code, len(snapshot.trades))
    if monitor.leader_momentum_last.get(key) == marker:
        return
    persisted = await monitor._event(
        strategy_repository,
        config,
        instrument_id=candidate.instrument_id,
        event_type="leader_momentum",
        state=snapshot.state,
        reason_code=snapshot.reason_code,
        observed_at=snapshot.as_of or bars[-1].end_time,
        payload={
            "arm": LEADER_MOMENTUM_ARM,
            "universe_id": universe.universe_id,
            "universe_discovery_source": universe.discovery_source,
            "morning_discovery_rank": candidate.discovery_rank,
            "policy": snapshot.model_dump(mode="json"),
            "research_only": True,
            "execution_authority": False,
        },
    )
    monitor.leader_momentum_last[key] = marker
    monitor.leader_momentum_event_count += int(persisted)


__all__ = [
    "LEADER_MOMENTUM_ARM",
    "LEADER_MOMENTUM_ENTRY_START_ET",
    "LEADER_MOMENTUM_LAST_ENTRY_ET",
    "leader_momentum_enabled",
    "record_leader_momentum",
]
