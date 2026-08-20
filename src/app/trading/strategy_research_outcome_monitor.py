from __future__ import annotations

import asyncio
import os
from contextlib import suppress
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import FastAPI

from .paper import PaperOrder
from .paper_runtime_repository import default_runtime_paper_repository
from .research.fact_repository import TradingFactRepository, default_fact_repository
from .research.outcome_dataset import build_research_outcome, research_context_as_of
from .strategy_repository import (
    StrategyProtection,
    TradingStrategyConfigDocument,
    TradingStrategyRepository,
    default_strategy_repository,
)
from .trade_logging import trade_log

_ET = ZoneInfo("America/New_York")
_STATE_KEY = "_omnix_trading_strategy_research_outcome_monitor"


def _flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def strategy_research_outcome_monitor_enabled() -> bool:
    if os.environ.get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return _flag("OMNIX_TRADING_RESEARCH_OUTCOME_MONITOR_IN_TESTS", "0")
    return _flag("OMNIX_TRADING_RESEARCH_OUTCOME_MONITOR", "1")


def _interval_seconds() -> float:
    try:
        value = float(os.environ.get("OMNIX_TRADING_RESEARCH_OUTCOME_INTERVAL_SECONDS", "30"))
    except ValueError:
        value = 30.0
    return max(10.0, value)


def _filled_at(order: PaperOrder) -> datetime | None:
    value = order.updated_at or order.created_at
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("paper_order_timestamp_must_be_timezone_aware")
    return value.astimezone(timezone.utc)


def capture_closed_paper_outcome(
    *,
    config: TradingStrategyConfigDocument,
    protection: StrategyProtection,
    entry_order: PaperOrder,
    exit_order: PaperOrder,
    fact_repository: TradingFactRepository,
) -> bool:
    """Append one research-attributed outcome for an already completed paper trade.

    This function is observational only. It never creates/cancels/modifies an order.
    Missing live MFE/MAE is represented explicitly through data-quality flags rather
    than reconstructed from later market data.
    """

    if protection.status != "closed":
        return False
    if entry_order.status != "filled" or exit_order.status != "filled":
        return False
    if entry_order.average_fill_price is None or exit_order.average_fill_price is None:
        return False
    entry_time = _filled_at(entry_order)
    exit_time = _filled_at(exit_order)
    if entry_time is None or exit_time is None or exit_time < entry_time:
        return False

    entry_price = entry_order.average_fill_price
    exit_price = exit_order.average_fill_price
    risk_per_share = entry_price - protection.stop_price
    if risk_per_share <= 0:
        return False

    r_result = (exit_price - entry_price) / risk_per_share
    features = fact_repository.research_features_as_of(protection.instrument_id, entry_time)
    context = research_context_as_of(
        instrument_id=protection.instrument_id,
        decision_at=entry_time,
        fact_repository=fact_repository,
    )
    research_fidelity = "captured_exact" if features is not None else "unavailable"
    hold_minutes = Decimal(str((exit_time - entry_time).total_seconds() / 60))
    target_exit = protection.trigger_reason == "profit_target"
    stop_exit = protection.trigger_reason == "protective_stop"
    two_r_before_minus_one_r = (
        target_exit if config.config.reward_multiple == Decimal("2") else None
    )
    flags = ["paper_live_mfe_unavailable", "paper_live_mae_unavailable"]
    if features is None:
        flags.append("research_features_unavailable_as_of_entry")
    if protection.trigger_reason == "position_closed":
        flags.append("exit_reason_external_or_reconciled")

    outcome = build_research_outcome(
        session_date=entry_time.astimezone(_ET).date(),
        strategy_id=config.strategy_id,
        instrument_id=protection.instrument_id,
        strategy_version=config.config.strategy_version,
        features=features,
        market_fidelity="paper-execution-v2",
        research_fidelity=research_fidelity,
        strategy_state="paper_closed",
        rejection_reason=None,
        entry_time=entry_time,
        exit_time=exit_time,
        mfe_r=None,
        mae_r=None,
        r_result=r_result,
        two_r_before_minus_one_r=two_r_before_minus_one_r,
        time_to_mfe_minutes=hold_minutes if target_exit else None,
        time_to_stop_minutes=hold_minutes if stop_exit else None,
        data_quality_flags=tuple(flags),
        research_context=context,
    )
    persisted = fact_repository.save_outcome(outcome)
    trade_log(
        "auto_trading",
        "paper_research_outcome_captured",
        strategy_id=config.strategy_id,
        strategy_version=config.config.strategy_version,
        instrument_id=protection.instrument_id,
        protection_id=protection.protection_id,
        entry_order_id=entry_order.order_id,
        exit_order_id=exit_order.order_id,
        entry_time=entry_time,
        exit_time=exit_time,
        entry_price=entry_price,
        exit_price=exit_price,
        stop_price=protection.stop_price,
        target_price=protection.target_price,
        r_result=r_result,
        trigger_reason=protection.trigger_reason,
        research_fidelity=research_fidelity,
        feature_id=features.feature_id if features is not None else None,
        research_context_present=bool(context),
        persisted=persisted,
        execution_authority=False,
    )
    return persisted


class TradingStrategyResearchOutcomeMonitor:
    def __init__(self, *, interval_seconds: float | None = None) -> None:
        self.interval_seconds = interval_seconds or _interval_seconds()
        self._task: asyncio.Task[None] | None = None
        self.last_run_at: datetime | None = None
        self.last_error: str | None = None
        self.capture_count = 0

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def run_once(self) -> int:
        strategy_repository: TradingStrategyRepository = default_strategy_repository()
        fact_repository = default_fact_repository()
        paper_repository = default_runtime_paper_repository()
        configs = await asyncio.to_thread(strategy_repository.list_configs, active_only=False)
        captured = 0
        snapshots: dict[str, object] = {}
        for config in configs:
            protections = await asyncio.to_thread(
                strategy_repository.list_protections,
                config.strategy_id,
                active_only=False,
            )
            closed = [
                item for item in protections
                if item.status == "closed" and item.exit_order_id is not None
            ]
            if not closed:
                continue
            snapshot = snapshots.get(config.account_id)
            if snapshot is None:
                snapshot = await asyncio.to_thread(paper_repository.snapshot, config.account_id)
                snapshots[config.account_id] = snapshot
            history = {order.order_id: order for order in snapshot.order_history}
            for protection in closed:
                entry = history.get(protection.entry_order_id)
                exit_order = history.get(protection.exit_order_id or "")
                if entry is None or exit_order is None:
                    continue
                try:
                    persisted = await asyncio.to_thread(
                        capture_closed_paper_outcome,
                        config=config,
                        protection=protection,
                        entry_order=entry,
                        exit_order=exit_order,
                        fact_repository=fact_repository,
                    )
                    captured += int(persisted)
                except Exception as exc:
                    self.last_error = (
                        f"{config.strategy_id}/{protection.protection_id}: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    trade_log(
                        "auto_trading",
                        "paper_research_outcome_capture_error",
                        strategy_id=config.strategy_id,
                        instrument_id=protection.instrument_id,
                        protection_id=protection.protection_id,
                        error_type=type(exc).__name__,
                        detail=str(exc),
                        execution_authority=False,
                    )
        self.capture_count += captured
        self.last_run_at = datetime.now(timezone.utc)
        return captured

    async def _loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                trade_log(
                    "auto_trading",
                    "paper_research_outcome_monitor_error",
                    error_type=type(exc).__name__,
                    detail=str(exc),
                    execution_authority=False,
                )
            await asyncio.sleep(self.interval_seconds)


def register_trading_strategy_research_outcome_monitor(
    gateway: FastAPI,
) -> TradingStrategyResearchOutcomeMonitor:
    existing = getattr(gateway.state, _STATE_KEY, None)
    if isinstance(existing, TradingStrategyResearchOutcomeMonitor):
        return existing
    monitor = TradingStrategyResearchOutcomeMonitor()
    setattr(gateway.state, _STATE_KEY, monitor)

    async def startup() -> None:
        if strategy_research_outcome_monitor_enabled():
            monitor.start()

    async def shutdown() -> None:
        await monitor.stop()

    gateway.router.add_event_handler("startup", startup)
    gateway.router.add_event_handler("shutdown", shutdown)
    return monitor


__all__ = [
    "TradingStrategyResearchOutcomeMonitor",
    "capture_closed_paper_outcome",
    "register_trading_strategy_research_outcome_monitor",
    "strategy_research_outcome_monitor_enabled",
]
