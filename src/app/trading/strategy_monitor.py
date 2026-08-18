from __future__ import annotations

import asyncio
import hashlib
import os
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI

from .gapper_dataset import GapperCandidate
from .paper import PaperMarketObservation, PaperOrderRequest, paper_protection_trigger
from .paper_repository import TradingPaperRepository
from .paper_runtime_repository import default_runtime_paper_repository
from .service import TradingMarketDataService, default_market_data_service
from .strategies.gap_pullback import evaluate_gap_pullback
from .strategies.models import GapPullbackResult
from .strategy_repository import (
    StrategyEvent,
    StrategyProtection,
    TradingStrategyConfigDocument,
    TradingStrategyRepository,
    default_strategy_repository,
)
from .strategy_risk import size_strategy_entry
from .strategy_timeframes import proposal_priority, resample_final_bars


_ET = ZoneInfo("America/New_York")
_STATE_KEY = "_omnix_trading_strategy_monitor"


def _flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def trading_strategy_monitor_enabled() -> bool:
    if os.environ.get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return _flag("OMNIX_TRADING_STRATEGY_MONITOR_IN_TESTS", "0")
    return _flag("OMNIX_TRADING_STRATEGY_MONITOR", "1")


def _interval_seconds() -> float:
    try:
        value = float(os.environ.get("OMNIX_TRADING_STRATEGY_INTERVAL_SECONDS", "30"))
    except ValueError:
        value = 30.0
    return max(5.0, value)


def _key(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()


def _paper_observation(execution) -> PaperMarketObservation:
    return PaperMarketObservation(
        instrument_id=execution.instrument_id,
        binding_id=execution.binding_id,
        provider=execution.provider,
        price=execution.last,
        bid=execution.bid,
        ask=execution.ask,
        bid_size=execution.bid_size,
        ask_size=execution.ask_size,
        high=execution.high,
        low=execution.low,
        volume=execution.bar_volume,
        bar_start_time=execution.bar_start_time,
        source_time=execution.source_time,
        evaluated_at=datetime.now(timezone.utc),
        execution_eligible=execution.execution_eligible,
        freshness_mode=execution.freshness_mode,
        rejection_reasons=execution.rejection_reasons,
        halted=execution.halted is True,
    )


@dataclass(frozen=True)
class _EntryProposal:
    candidate: GapperCandidate
    result: GapPullbackResult
    observed_at: datetime

    @property
    def priority(self) -> tuple[datetime, int, int, str]:
        quality_score = (
            self.result.signal.quality_score
            if self.result.signal is not None
            else self.result.features.quality_score
        )
        return proposal_priority(
            observed_at=self.observed_at,
            quality_score=quality_score,
            discovery_rank=self.candidate.discovery_rank,
            instrument_id=self.candidate.instrument_id,
        )


class TradingStrategyMonitor:
    """Deterministic strategy runner with OFF/SHADOW/AUTO_PAPER modes only.

    AUTO_PAPER can create orders exclusively in the existing paper repository.
    There is intentionally no live-broker adapter or AI order-placement path.
    """

    def __init__(
        self,
        *,
        strategy_repository_factory: Callable[[], TradingStrategyRepository] = default_strategy_repository,
        paper_repository_factory: Callable[[], TradingPaperRepository] = default_runtime_paper_repository,
        market_service_factory: Callable[[], TradingMarketDataService] = default_market_data_service,
        interval_seconds: float | None = None,
    ) -> None:
        self.strategy_repository_factory = strategy_repository_factory
        self.paper_repository_factory = paper_repository_factory
        self.market_service_factory = market_service_factory
        self.interval_seconds = interval_seconds or _interval_seconds()
        self._task: asyncio.Task[None] | None = None
        self.last_run_at: datetime | None = None
        self.last_error: str | None = None
        self.evaluation_count = 0
        self.signal_count = 0
        self.paper_order_count = 0
        self.rejection_count = 0

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

    async def _event(
        self,
        repository: TradingStrategyRepository,
        config: TradingStrategyConfigDocument,
        *,
        instrument_id: str,
        event_type: str,
        state: str,
        reason_code: str,
        observed_at: datetime,
        payload: dict[str, object] | None = None,
    ) -> bool:
        idem = _key(
            config.strategy_id,
            instrument_id,
            event_type,
            state,
            reason_code,
            observed_at.isoformat(),
        )
        return await asyncio.to_thread(
            repository.append_event,
            StrategyEvent(
                strategy_id=config.strategy_id,
                event_id=idem[:32],
                instrument_id=instrument_id,
                event_type=event_type,
                state=state,
                reason_code=reason_code,
                observed_at=observed_at,
                idempotency_key=idem,
                payload=payload or {},
            ),
        )

    async def _reconcile_protections(
        self,
        config: TradingStrategyConfigDocument,
        strategy_repository: TradingStrategyRepository,
        paper_repository: TradingPaperRepository,
        market_service: TradingMarketDataService,
    ) -> None:
        protections = await asyncio.to_thread(
            strategy_repository.list_protections,
            config.strategy_id,
            active_only=True,
        )
        if not protections:
            return
        snapshot = await asyncio.to_thread(paper_repository.snapshot, config.account_id)
        history = {order.order_id: order for order in snapshot.order_history}
        positions = {position.instrument_id: position for position in snapshot.positions}
        now_et = datetime.now(timezone.utc).astimezone(_ET)
        force_flat = now_et.time() >= config.risk.force_flat_et
        for protection in protections:
            entry_order = history.get(protection.entry_order_id)
            if protection.status == "pending_entry":
                if entry_order is not None and entry_order.status == "filled":
                    position = positions.get(protection.instrument_id)
                    if position is not None and position.quantity > 0:
                        protection.status = "active"
                        protection.quantity = min(protection.quantity, position.quantity)
                        await asyncio.to_thread(strategy_repository.save_protection, protection)
                elif entry_order is not None and entry_order.status in {"rejected", "cancelled"}:
                    protection.status = "cancelled"
                    protection.trigger_reason = f"entry_{entry_order.status}"
                    await asyncio.to_thread(strategy_repository.save_protection, protection)
                continue

            if protection.status == "exit_submitted":
                exit_order = history.get(protection.exit_order_id or "")
                if exit_order is not None and exit_order.status == "filled":
                    protection.status = "closed"
                    await asyncio.to_thread(strategy_repository.save_protection, protection)
                elif exit_order is not None and exit_order.status in {"rejected", "cancelled"}:
                    protection.status = "active"
                    protection.exit_order_id = None
                    protection.trigger_reason = f"exit_{exit_order.status}_retry"
                    await asyncio.to_thread(strategy_repository.save_protection, protection)
                continue

            if protection.status != "active":
                continue
            position = positions.get(protection.instrument_id)
            if position is None or position.quantity <= 0:
                protection.status = "closed"
                protection.trigger_reason = "position_closed"
                await asyncio.to_thread(strategy_repository.save_protection, protection)
                continue

            conflicting_exit = any(
                order.status == "open"
                and order.instrument_id == protection.instrument_id
                and order.side == "sell"
                for order in snapshot.open_orders
            )
            if conflicting_exit:
                continue

            binding_id = entry_order.binding_id if entry_order is not None else None
            try:
                execution = await asyncio.to_thread(
                    market_service.execution_observation,
                    protection.instrument_id,
                    binding_id,
                )
            except Exception as exc:
                self.last_error = f"protection_data: {type(exc).__name__}: {exc}"
                continue
            if not execution.execution_eligible:
                continue
            trigger = None
            if force_flat:
                trigger = "force_flat"
            else:
                activated_at = None
                if entry_order is not None:
                    activated_at = entry_order.updated_at or entry_order.created_at
                trigger_kind = paper_protection_trigger(
                    is_long=True,
                    stop_price=protection.stop_price,
                    target_price=protection.target_price,
                    observation=_paper_observation(execution),
                    activated_at=activated_at,
                )
                if trigger_kind == "stop":
                    trigger = "protective_stop"
                elif trigger_kind == "target":
                    trigger = "profit_target"
            if trigger is None:
                continue
            quantity = min(protection.quantity, position.quantity)
            order_id = f"exit-{protection.protection_id}"[:200]
            idem = _key(config.strategy_id, protection.protection_id, trigger)
            try:
                await asyncio.to_thread(
                    paper_repository.place_order,
                    config.account_id,
                    PaperOrderRequest(
                        order_id=order_id,
                        instrument_id=protection.instrument_id,
                        binding_id=binding_id,
                        side="sell",
                        order_type="market",
                        quantity=quantity,
                        reference_price=execution.bid or execution.last,
                        idempotency_key=idem,
                    ),
                )
            except ValueError as exc:
                self.last_error = f"protection_order: {exc}"
                continue
            protection.exit_order_id = order_id
            protection.status = "exit_submitted"
            protection.trigger_reason = trigger
            await asyncio.to_thread(strategy_repository.save_protection, protection)

    async def _evaluate_candidates(
        self,
        config: TradingStrategyConfigDocument,
        strategy_repository: TradingStrategyRepository,
        market_service: TradingMarketDataService,
        universe,
    ) -> list[_EntryProposal]:
        proposals: list[_EntryProposal] = []
        for candidate in universe.candidates:
            try:
                response = await asyncio.to_thread(
                    market_service.bars,
                    candidate.instrument_id,
                    "1m",
                    240,
                    candidate.binding_id,
                )
                base_bars = [bar for bar in response.bars if bar.is_final]
                execution_bars = resample_final_bars(
                    base_bars,
                    config.config.execution_interval,
                )
                structure_bars = resample_final_bars(
                    base_bars,
                    config.config.structure_interval,
                )
            except Exception as exc:
                self.last_error = f"strategy_bars: {type(exc).__name__}: {exc}"
                continue
            if not execution_bars or not structure_bars:
                continue
            result = evaluate_gap_pullback(candidate, structure_bars, config.config)
            observed_at = structure_bars[-1].end_time
            self.evaluation_count += 1
            await self._event(
                strategy_repository,
                config,
                instrument_id=candidate.instrument_id,
                event_type="state",
                state=result.state,
                reason_code=result.reason_code,
                observed_at=observed_at,
                payload={
                    "features": result.features.model_dump(mode="json"),
                    "transitions": list(result.transitions),
                    "mode": config.mode,
                    "universe_id": universe.universe_id,
                    "structure_interval": config.config.structure_interval,
                    "execution_interval": config.config.execution_interval,
                    "structure_bar_count": len(structure_bars),
                    "execution_bar_count": len(execution_bars),
                },
            )
            if result.state == "entry_ready" and result.signal is not None:
                self.signal_count += 1
                proposals.append(
                    _EntryProposal(
                        candidate=candidate,
                        result=result,
                        observed_at=observed_at,
                    )
                )
        proposals.sort(key=lambda proposal: proposal.priority)
        return proposals

    async def _run_config(
        self,
        config: TradingStrategyConfigDocument,
        strategy_repository: TradingStrategyRepository,
        paper_repository: TradingPaperRepository,
        market_service: TradingMarketDataService,
    ) -> None:
        await self._reconcile_protections(
            config,
            strategy_repository,
            paper_repository,
            market_service,
        )
        if config.mode == "off" or not config.enabled or not config.active_universe_id:
            return

        now_utc = datetime.now(timezone.utc)
        now_et = now_utc.astimezone(_ET)
        today_et = now_et.date()
        day_start_et = datetime(today_et.year, today_et.month, today_et.day, tzinfo=_ET)
        day_end_et = day_start_et + timedelta(days=1)

        universe = await asyncio.to_thread(
            strategy_repository.get_universe,
            config.active_universe_id,
        )
        if universe.session_date != today_et:
            rejection_time = day_start_et.astimezone(timezone.utc)
            for candidate in universe.candidates:
                self.rejection_count += 1
                await self._event(
                    strategy_repository,
                    config,
                    instrument_id=candidate.instrument_id,
                    event_type="rejection",
                    state="rejected",
                    reason_code="UNIVERSE_SESSION_MISMATCH",
                    observed_at=rejection_time,
                    payload={
                        "universe_id": universe.universe_id,
                        "universe_session_date": universe.session_date.isoformat(),
                        "runtime_session_date": today_et.isoformat(),
                    },
                )
            return

        proposals = await self._evaluate_candidates(
            config,
            strategy_repository,
            market_service,
            universe,
        )
        if config.mode != "auto_paper" or not proposals:
            return

        snapshot = await asyncio.to_thread(paper_repository.snapshot, config.account_id)
        if hasattr(strategy_repository, "entry_events_between"):
            entry_events = await asyncio.to_thread(
                strategy_repository.entry_events_between,
                config.strategy_id,
                start_time=day_start_et,
                end_time=day_end_et,
            )
        else:
            recent_events = await asyncio.to_thread(
                strategy_repository.recent_events,
                config.strategy_id,
                500,
            )
            entry_events = [
                event
                for event in recent_events
                if event.event_type == "entry_order_submitted"
                and event.observed_at.astimezone(_ET).date() == today_et
            ]
        trades_today = len(entry_events)
        traded_symbols = {event.instrument_id for event in entry_events}

        daily_realized_pnl: Decimal | None = None
        if hasattr(strategy_repository, "daily_paper_pnl"):
            daily_realized_pnl = await asyncio.to_thread(
                strategy_repository.daily_paper_pnl,
                config.account_id,
                start_time=day_start_et,
                end_time=day_end_et,
            )

        protections = await asyncio.to_thread(
            strategy_repository.list_protections,
            config.strategy_id,
            active_only=True,
        )
        protected_symbols = {item.instrument_id for item in protections}
        open_risk = sum(
            (
                item.quantity
                * (item.target_price - item.stop_price)
                / (config.config.reward_multiple + Decimal("1"))
                for item in protections
                if item.status in {"pending_entry", "active"}
            ),
            Decimal("0"),
        )

        for proposal in proposals:
            candidate = proposal.candidate
            result = proposal.result
            assert result.signal is not None
            observed_at = proposal.observed_at
            if candidate.instrument_id in protected_symbols:
                continue
            try:
                execution = await asyncio.to_thread(
                    market_service.execution_observation,
                    candidate.instrument_id,
                    candidate.binding_id,
                )
            except Exception as exc:
                self.rejection_count += 1
                await self._event(
                    strategy_repository,
                    config,
                    instrument_id=candidate.instrument_id,
                    event_type="rejection",
                    state=result.state,
                    reason_code="DATA_UNAVAILABLE",
                    observed_at=observed_at,
                    payload={"detail": str(exc)},
                )
                continue
            if not execution.execution_eligible:
                self.rejection_count += 1
                await self._event(
                    strategy_repository,
                    config,
                    instrument_id=candidate.instrument_id,
                    event_type="rejection",
                    state=result.state,
                    reason_code="DATA_STALE_OR_INELIGIBLE",
                    observed_at=observed_at,
                    payload={"reasons": list(execution.rejection_reasons)},
                )
                continue
            decision = size_strategy_entry(
                snapshot,
                result.signal,
                config.risk,
                spread_bps=execution.spread_bps,
                trades_today=trades_today,
                traded_symbols_today=traded_symbols,
                reserved_instruments=protected_symbols,
                daily_realized_pnl=daily_realized_pnl,
                open_strategy_risk=open_risk,
                observed_at=now_utc,
            )
            if not decision.allowed:
                self.rejection_count += 1
                await self._event(
                    strategy_repository,
                    config,
                    instrument_id=candidate.instrument_id,
                    event_type="rejection",
                    state=result.state,
                    reason_code=decision.reason_code,
                    observed_at=observed_at,
                    payload=decision.model_dump(mode="json"),
                )
                continue

            day = today_et.isoformat()
            order_key = _key(config.strategy_id, day, candidate.instrument_id, "entry")
            order_id = f"strat-{order_key[:32]}"
            try:
                await asyncio.to_thread(
                    paper_repository.place_order,
                    config.account_id,
                    PaperOrderRequest(
                        order_id=order_id,
                        instrument_id=candidate.instrument_id,
                        binding_id=candidate.binding_id,
                        side="buy",
                        order_type="market",
                        quantity=decision.quantity,
                        reference_price=execution.ask or execution.last,
                        idempotency_key=order_key,
                    ),
                )
            except ValueError as exc:
                self.rejection_count += 1
                await self._event(
                    strategy_repository,
                    config,
                    instrument_id=candidate.instrument_id,
                    event_type="rejection",
                    state=result.state,
                    reason_code="PAPER_ORDER_REJECTED",
                    observed_at=observed_at,
                    payload={"detail": str(exc)},
                )
                continue

            protection = StrategyProtection(
                strategy_id=config.strategy_id,
                protection_id=f"prot-{order_key[:32]}",
                account_id=config.account_id,
                instrument_id=candidate.instrument_id,
                entry_order_id=order_id,
                stop_price=result.signal.stop_price,
                target_price=result.signal.target_price,
                quantity=decision.quantity,
                status="pending_entry",
            )
            await asyncio.to_thread(strategy_repository.save_protection, protection)
            await self._event(
                strategy_repository,
                config,
                instrument_id=candidate.instrument_id,
                event_type="entry_order_submitted",
                state="entry_ready",
                reason_code="AUTO_PAPER_ENTRY_SUBMITTED",
                observed_at=observed_at,
                payload={
                    "order_id": order_id,
                    "quantity": str(decision.quantity),
                    "stop_price": str(result.signal.stop_price),
                    "target_price": str(result.signal.target_price),
                    "quality_score": result.signal.quality_score,
                    "structure_interval": config.config.structure_interval,
                    "execution_interval": config.config.execution_interval,
                    "priority": [
                        observed_at.astimezone(timezone.utc).isoformat(),
                        -result.signal.quality_score,
                        candidate.discovery_rank if candidate.discovery_rank is not None else 10**9,
                        candidate.instrument_id,
                    ],
                },
            )
            self.paper_order_count += 1
            trades_today += 1
            traded_symbols.add(candidate.instrument_id)
            protected_symbols.add(candidate.instrument_id)
            open_risk += decision.estimated_risk

    async def run_once(self) -> int:
        strategy_repository = self.strategy_repository_factory()
        paper_repository = self.paper_repository_factory()
        market_service = self.market_service_factory()
        configs = await asyncio.to_thread(strategy_repository.list_configs, active_only=True)
        before = self.paper_order_count
        for config in configs:
            try:
                await self._run_config(config, strategy_repository, paper_repository, market_service)
            except Exception as exc:
                self.last_error = f"{config.strategy_id}: {type(exc).__name__}: {exc}"
        self.last_run_at = datetime.now(timezone.utc)
        return self.paper_order_count - before

    def diagnostics(self) -> dict[str, Any]:
        return {
            "enabled": trading_strategy_monitor_enabled(),
            "running": self._task is not None,
            "interval_seconds": self.interval_seconds,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_error": self.last_error,
            "evaluation_count": self.evaluation_count,
            "signal_count": self.signal_count,
            "paper_order_count": self.paper_order_count,
            "rejection_count": self.rejection_count,
            "candidate_arbitration": "observed_at_quality_score_discovery_rank_instrument",
            "live_broker_enabled": False,
            "ai_order_placement_enabled": False,
        }

    async def _loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
            await asyncio.sleep(self.interval_seconds)


def register_trading_strategy_monitor(gateway: FastAPI) -> TradingStrategyMonitor:
    existing = getattr(gateway.state, _STATE_KEY, None)
    if isinstance(existing, TradingStrategyMonitor):
        return existing
    monitor = TradingStrategyMonitor()
    setattr(gateway.state, _STATE_KEY, monitor)

    async def startup() -> None:
        if trading_strategy_monitor_enabled():
            monitor.start()

    async def shutdown() -> None:
        await monitor.stop()

    gateway.router.add_event_handler("startup", startup)
    gateway.router.add_event_handler("shutdown", shutdown)
    return monitor
