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
from .indicators.engine import relative_strength_index
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
from .strategy_intraday_learning import IntradayLearningSnapshot, build_intraday_learning_snapshot
from .strategy_research_policy import apply_research_policy_to_quality, resolve_strategy_research_policy
from .strategy_risk import size_strategy_entry
from .strategy_shadow_execution import observe_shadow_execution
from .strategy_shadow_universe import resolve_v2_shadow_archive
from .strategy_v2_qualification import (
    V2_PROSPECTIVE_START,
    V2_QUALIFICATION_EVENT_TYPES,
    evaluate_v2_prospective_qualification,
    v2_profile_fingerprint,
)
from .strategy_v2_management import (
    v2_active_stop_for_prior_high,
    v2_hold_expired,
    v2_initial_stop_from_target,
    v2_management_levels,
)
from .strategy_timeframes import proposal_priority, resample_final_bars
from .trade_logging import trade_log


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


def _trade_attempt_id(strategy_id: str, instrument_id: str, observed_at: datetime) -> str:
    """Stable identity for one causal finalized-bar entry opportunity."""
    digest = _key(
        strategy_id,
        instrument_id,
        observed_at.astimezone(timezone.utc).isoformat(),
        "long-entry-signal",
    )
    return f"attempt-{digest[:24]}"


def _v2_qualification_events(
    repository: TradingStrategyRepository,
    strategy_id: str,
    *,
    now: datetime,
) -> list[StrategyEvent]:
    start = datetime(
        V2_PROSPECTIVE_START.year,
        V2_PROSPECTIVE_START.month,
        V2_PROSPECTIVE_START.day,
        tzinfo=timezone.utc,
    )
    end = now.astimezone(timezone.utc) + timedelta(seconds=1)
    if hasattr(repository, "events_by_types_between"):
        return repository.events_by_types_between(
            strategy_id,
            event_types=V2_QUALIFICATION_EVENT_TYPES,
            start_time=start,
            end_time=end,
            limit=20_000,
        )
    return [
        event
        for event in repository.recent_events(strategy_id, 20_000)
        if event.event_type in V2_QUALIFICATION_EVENT_TYPES
        and start <= event.observed_at.astimezone(timezone.utc) < end
    ]


def _run_id(prefix: str, observed_at: datetime) -> str:
    return f"{prefix}-{observed_at.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}"


def _execution_audit_payload(execution) -> dict[str, object]:
    fields = (
        "instrument_id",
        "binding_id",
        "provider",
        "last",
        "bid",
        "ask",
        "bid_size",
        "ask_size",
        "high",
        "low",
        "bar_volume",
        "bar_start_time",
        "source_time",
        "spread_bps",
        "execution_eligible",
        "freshness_mode",
        "rejection_reasons",
        "halted",
    )
    return {field: getattr(execution, field, None) for field in fields}


def _bar_audit_payload(bar) -> dict[str, object]:
    fields = (
        "instrument_id",
        "interval",
        "start_time",
        "end_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "provider",
        "session",
        "is_final",
    )
    return {field: getattr(bar, field, None) for field in fields}


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


_BASIC_MARKET_REJECTIONS = {
    "GAP_BELOW_MINIMUM",
    "PRICE_OUT_OF_RANGE",
    "PREMARKET_DOLLAR_VOLUME_LOW",
    "TOD_RVOL_MISSING",
    "TOD_RVOL_LOW",
    "SPREAD_MISSING",
    "SPREAD_TOO_WIDE",
}
_RESEARCH_SUPPLY_REJECTIONS = {
    "CATALYST_EVIDENCE_REQUIRED",
    "DILUTION_SUPPLY_RISK",
    "FLOAT_OUTSIDE_REQUIRED_RANGE",
}


def _candidate_lifecycle_stage(result: GapPullbackResult) -> int:
    """Highest lifecycle rank actually proven by this causal evaluation."""
    transitions = set(result.transitions)
    if result.state == "entry_ready":
        return 4
    if "higher_low_confirmed" in transitions or result.state in {
        "higher_low_confirmed", "vwap_reclaim", "lower_high_break", "breakout_hold"
    }:
        return 3
    if result.reason_code in _BASIC_MARKET_REJECTIONS:
        return 0
    if result.reason_code in _RESEARCH_SUPPLY_REJECTIONS:
        return 1
    if "qualified_gap" in transitions or result.state not in {"discovered", "rejected"}:
        return 2
    return 0


def _rsi_crossed_after_activation(
    bars,
    *,
    period: int,
    threshold: Decimal,
    activated_at: datetime,
    observed_at: datetime,
) -> bool:
    """Return true when any finalized post-entry bar confirms the configured RSI cross.

    RSI values use the same shared indicator implementation as the portfolio
    backtester. Looking across all bars since activation prevents a 30-second
    monitor from missing a cross that occurred between polling cycles.
    """
    session_date = activated_at.astimezone(_ET).date()
    finalized = sorted(
        (
            bar for bar in bars
            if bar.is_final
            and bar.end_time <= observed_at
            and bar.start_time.astimezone(_ET).date() == session_date
        ),
        key=lambda bar: bar.start_time,
    )
    values = relative_strength_index([bar.close for bar in finalized], period)
    for index in range(1, len(values)):
        bar_index = period + index
        if bar_index >= len(finalized) or finalized[bar_index].end_time <= activated_at:
            continue
        if values[index - 1] >= threshold and values[index] < threshold:
            return True
    return False


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
        self.current_run_id: str | None = None
        self.last_run_at: datetime | None = None
        self.last_error: str | None = None
        self.evaluation_count = 0
        self.signal_count = 0
        self.paper_order_count = 0
        self.rejection_count = 0
        self.intraday_learning_snapshot_count = 0

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
                run_id=self.current_run_id,
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
        trade_log(
            "auto_trading",
            "protection_reconcile_start",
            run_id=self.current_run_id,
            strategy_id=config.strategy_id,
            account_id=config.account_id,
            protection_count=len(protections),
            force_flat=force_flat,
            force_flat_et=config.risk.force_flat_et,
        )
        for protection in protections:
            entry_order = history.get(protection.entry_order_id)
            if protection.status == "pending_entry":
                if entry_order is not None and entry_order.status == "filled":
                    position = positions.get(protection.instrument_id)
                    if position is not None and position.quantity > 0:
                        activated_at = entry_order.updated_at or entry_order.created_at or datetime.now(timezone.utc)
                        fill_price = entry_order.average_fill_price
                        if protection.initial_stop_price is None:
                            protection.initial_stop_price = protection.stop_price
                        if fill_price is not None:
                            protection.mae_price = fill_price if protection.mae_price is None else min(protection.mae_price, fill_price)
                            protection.mfe_price = fill_price if protection.mfe_price is None else max(protection.mfe_price, fill_price)
                        if config.config.strategy_version == "2.0.0":
                            if fill_price is None:
                                self.last_error = "v2_protection: filled entry missing average_fill_price"
                                trade_log(
                                    "auto_trading",
                                    "v2_protection_activation_deferred",
                                    run_id=self.current_run_id,
                                    strategy_id=config.strategy_id,
                                    instrument_id=protection.instrument_id,
                                    entry_order_id=entry_order.order_id,
                                    reason="missing_average_fill_price",
                                )
                                continue
                            try:
                                levels = v2_management_levels(
                                    config.config,
                                    entry_price=fill_price,
                                    initial_stop=protection.stop_price,
                                )
                            except ValueError as exc:
                                self.last_error = f"v2_protection: {exc}"
                                trade_log(
                                    "auto_trading",
                                    "v2_protection_activation_deferred",
                                    run_id=self.current_run_id,
                                    strategy_id=config.strategy_id,
                                    instrument_id=protection.instrument_id,
                                    entry_order_id=entry_order.order_id,
                                    reason="invalid_fill_anchored_risk",
                                    detail=str(exc),
                                )
                                continue
                            # Match the V11 backtester: keep the structural L2 stop,
                            # but anchor R/target to the actual pessimistic fill.
                            protection.target_price = levels.target_price
                            protection.initial_target_price = levels.target_price
                        elif protection.initial_target_price is None:
                            protection.initial_target_price = protection.target_price
                        protection.status = "active"
                        protection.quantity = min(protection.quantity, position.quantity)
                        saved = await asyncio.to_thread(strategy_repository.save_protection, protection)
                        if config.config.strategy_version == "2.0.0":
                            await self._event(
                                strategy_repository,
                                config,
                                instrument_id=protection.instrument_id,
                                event_type="protection",
                                state="active",
                                reason_code="V2_PROTECTION_ANCHORED_TO_FILL",
                                observed_at=activated_at,
                                payload={
                                    "entry_fill_price": str(entry_order.average_fill_price),
                                    "initial_stop": str(saved.stop_price),
                                    "target_price": str(saved.target_price),
                                    "reward_multiple": str(config.config.reward_multiple),
                                    "profit_protection_trigger_r": str(config.config.v2_profit_protection_trigger_r),
                                    "protected_stop_r": str(config.config.v2_protected_stop_r),
                                    "max_hold_minutes": config.config.v2_max_hold_minutes,
                                },
                            )
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
                trade_log(
                    "auto_trading",
                    "protection_exit_skipped",
                    run_id=self.current_run_id,
                    strategy_id=config.strategy_id,
                    instrument_id=protection.instrument_id,
                    protection_id=protection.protection_id,
                    reason="conflicting_open_sell_order",
                )
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
                trade_log(
                    "auto_trading",
                    "protection_execution_error",
                    run_id=self.current_run_id,
                    strategy_id=config.strategy_id,
                    instrument_id=protection.instrument_id,
                    protection_id=protection.protection_id,
                    error_type=type(exc).__name__,
                    detail=str(exc),
                )
                continue
            if not execution.execution_eligible:
                trade_log(
                    "auto_trading",
                    "protection_execution_ineligible",
                    run_id=self.current_run_id,
                    strategy_id=config.strategy_id,
                    instrument_id=protection.instrument_id,
                    protection_id=protection.protection_id,
                    execution=_execution_audit_payload(execution),
                )
                continue
            trigger = None
            activated_at = None
            if entry_order is not None:
                activated_at = entry_order.updated_at or entry_order.created_at

            if activated_at is not None and entry_order is not None and entry_order.average_fill_price is not None:
                mark = execution.last or execution.bid or execution.ask
                if mark is not None:
                    range_is_post_entry = (
                        execution.bar_start_time is not None
                        and execution.bar_start_time >= activated_at
                    )
                    observed_low = execution.low if range_is_post_entry and execution.low is not None else mark
                    observed_high = execution.high if range_is_post_entry and execution.high is not None else mark
                    next_mae = observed_low if protection.mae_price is None else min(protection.mae_price, observed_low)
                    next_mfe = observed_high if protection.mfe_price is None else max(protection.mfe_price, observed_high)
                    if next_mae != protection.mae_price or next_mfe != protection.mfe_price:
                        protection.mae_price = next_mae
                        protection.mfe_price = next_mfe
                        protection = await asyncio.to_thread(strategy_repository.save_protection, protection)

            if (
                config.config.strategy_version == "2.0.0"
                and entry_order is not None
                and entry_order.average_fill_price is not None
                and activated_at is not None
            ):
                entry_price = entry_order.average_fill_price
                try:
                    initial_stop = protection.initial_stop_price or v2_initial_stop_from_target(
                        config.config,
                        entry_price=entry_price,
                        target_price=protection.target_price,
                    )
                    response = await asyncio.to_thread(
                        market_service.bars,
                        protection.instrument_id,
                        "1m",
                        240,
                        binding_id,
                    )
                    finalized = [
                        bar
                        for bar in response.bars
                        if bar.is_final
                        and bar.end_time > activated_at
                        and bar.end_time <= execution.source_time
                    ]
                    prior_high = max(
                        [entry_price, *(bar.high for bar in finalized)],
                    )
                    desired_stop = v2_active_stop_for_prior_high(
                        config.config,
                        entry_price=entry_price,
                        initial_stop=initial_stop,
                        prior_finalized_high=prior_high,
                    )
                    if desired_stop > protection.stop_price:
                        old_stop = protection.stop_price
                        protection.stop_price = desired_stop
                        protection.trigger_reason = "profit_protection_armed"
                        protection = await asyncio.to_thread(
                            strategy_repository.save_protection, protection
                        )
                        await self._event(
                            strategy_repository,
                            config,
                            instrument_id=protection.instrument_id,
                            event_type="protection",
                            state="active",
                            reason_code="V2_PROFIT_PROTECTION_ARMED",
                            observed_at=execution.source_time,
                            payload={
                                "old_stop": str(old_stop),
                                "new_stop": str(protection.stop_price),
                                "entry_fill_price": str(entry_price),
                                "prior_finalized_high": str(prior_high),
                                "trigger_r": str(config.config.v2_profit_protection_trigger_r),
                                "protected_stop_r": str(config.config.v2_protected_stop_r),
                                "finalized_bar_count_since_entry": len(finalized),
                            },
                        )
                except Exception as exc:
                    # Static structural protection remains active if the optional
                    # profit-protection evidence cannot be refreshed this cycle.
                    self.last_error = f"v2_protection_management: {type(exc).__name__}: {exc}"
                    trade_log(
                        "auto_trading",
                        "v2_protection_management_error",
                        run_id=self.current_run_id,
                        strategy_id=config.strategy_id,
                        instrument_id=protection.instrument_id,
                        error_type=type(exc).__name__,
                        detail=str(exc),
                    )

            if config.config.strategy_version != "2.0.0" and force_flat:
                # Preserve the original 1.x contract exactly: once force-flat
                # time is reached, EOD liquidation wins over stop/target checks.
                trigger = "force_flat"
            else:
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

                if trigger is None and activated_at is not None:
                    try:
                        indicator_response = await asyncio.to_thread(
                            market_service.bars,
                            protection.instrument_id,
                            config.config.execution_interval,
                            240,
                            binding_id,
                        )
                        if _rsi_crossed_after_activation(
                            indicator_response.bars,
                            period=config.config.exit_rsi_period,
                            threshold=config.config.exit_rsi_threshold,
                            activated_at=activated_at,
                            observed_at=execution.source_time,
                        ):
                            trigger = "rsi"
                    except Exception as exc:
                        # Indicator refresh is diagnostic/fail-safe only: static
                        # stop/target and force-flat protection remain authoritative.
                        self.last_error = f"protection_rsi: {type(exc).__name__}: {exc}"
                        trade_log(
                            "auto_trading",
                            "protection_rsi_error",
                            run_id=self.current_run_id,
                            strategy_id=config.strategy_id,
                            instrument_id=protection.instrument_id,
                            error_type=type(exc).__name__,
                            detail=str(exc),
                        )

                if (
                    trigger is None
                    and config.config.strategy_version == "2.0.0"
                    and activated_at is not None
                    and v2_hold_expired(
                        config.config,
                        activated_at=activated_at,
                        observed_at=execution.source_time,
                    )
                ):
                    trigger = "max_hold"
                elif trigger is None and force_flat:
                    trigger = "force_flat"
            if trigger is None:
                continue
            quantity = min(protection.quantity, position.quantity)
            order_id = f"exit-{protection.protection_id}"[:200]
            idem = _key(config.strategy_id, protection.protection_id, trigger)
            trade_log(
                "auto_trading",
                "protection_triggered",
                run_id=self.current_run_id,
                strategy_id=config.strategy_id,
                account_id=config.account_id,
                instrument_id=protection.instrument_id,
                protection_id=protection.protection_id,
                trigger=trigger,
                quantity=quantity,
                stop_price=protection.stop_price,
                target_price=protection.target_price,
                position_quantity=position.quantity,
                execution=_execution_audit_payload(execution),
            )
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
                trade_log(
                    "auto_trading",
                    "protection_exit_order_rejected",
                    run_id=self.current_run_id,
                    strategy_id=config.strategy_id,
                    account_id=config.account_id,
                    instrument_id=protection.instrument_id,
                    protection_id=protection.protection_id,
                    order_id=order_id,
                    trigger=trigger,
                    detail=str(exc),
                    execution=_execution_audit_payload(execution),
                )
                continue
            protection.exit_order_id = order_id
            protection.status = "exit_submitted"
            protection.trigger_reason = trigger
            await asyncio.to_thread(strategy_repository.save_protection, protection)
            trade_log(
                "auto_trading",
                "protection_exit_order_submitted",
                run_id=self.current_run_id,
                strategy_id=config.strategy_id,
                account_id=config.account_id,
                instrument_id=protection.instrument_id,
                protection_id=protection.protection_id,
                order_id=order_id,
                trigger=trigger,
                quantity=quantity,
                reference_price=execution.bid or execution.last,
            )

    async def _evaluate_candidates(
        self,
        config: TradingStrategyConfigDocument,
        strategy_repository: TradingStrategyRepository,
        market_service: TradingMarketDataService,
        universe,
    ) -> list[_EntryProposal]:
        proposals: list[_EntryProposal] = []
        learning_rows: list[tuple[GapperCandidate, GapPullbackResult, datetime, IntradayLearningSnapshot]] = []
        for candidate in universe.candidates:
            try:
                response = await asyncio.to_thread(
                    market_service.bars,
                    candidate.instrument_id,
                    "1m",
                    500,
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
                trade_log(
                    "auto_trading",
                    "candidate_bars_error",
                    run_id=self.current_run_id,
                    strategy_id=config.strategy_id,
                    universe_id=universe.universe_id,
                    instrument_id=candidate.instrument_id,
                    binding_id=candidate.binding_id,
                    error_type=type(exc).__name__,
                    detail=str(exc),
                )
                continue
            if not execution_bars or not structure_bars:
                trade_log(
                    "auto_trading",
                    "candidate_bars_unusable",
                    run_id=self.current_run_id,
                    strategy_id=config.strategy_id,
                    universe_id=universe.universe_id,
                    instrument_id=candidate.instrument_id,
                    binding_id=candidate.binding_id,
                    finalized_bar_count=len(base_bars),
                    structure_bar_count=len(structure_bars),
                    execution_bar_count=len(execution_bars),
                )
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
                    "lifecycle_stage": _candidate_lifecycle_stage(result),
                    "strategy_version": config.config.strategy_version,
                    "profile_fingerprint": (
                        v2_profile_fingerprint(config.config)
                        if config.config.strategy_version == "2.0.0"
                        else config.config.strategy_version
                    ),
                    "mode": config.mode,
                    "universe_id": universe.universe_id,
                    "structure_interval": config.config.structure_interval,
                    "execution_interval": config.config.execution_interval,
                    "structure_bar_count": len(structure_bars),
                    "execution_bar_count": len(execution_bars),
                    "latest_structure_bar": _bar_audit_payload(structure_bars[-1]),
                    "latest_execution_bar": _bar_audit_payload(execution_bars[-1]),
                },
            )
            if config.config.intraday_learning_enabled:
                try:
                    learning = build_intraday_learning_snapshot(candidate, result, base_bars)
                except Exception as exc:
                    trade_log(
                        "auto_trading",
                        "intraday_learning_snapshot_error",
                        run_id=self.current_run_id,
                        strategy_id=config.strategy_id,
                        universe_id=universe.universe_id,
                        instrument_id=candidate.instrument_id,
                        error_type=type(exc).__name__,
                        detail=str(exc),
                        execution_authority=False,
                    )
                else:
                    learning_rows.append((candidate, result, observed_at, learning))
            if result.state == "entry_ready" and result.signal is not None:
                self.signal_count += 1
                if config.config.strategy_version == "1.2.0":
                    try:
                        research_decision = await asyncio.to_thread(
                            resolve_strategy_research_policy,
                            strategy_version=config.config.strategy_version,
                            instrument_id=candidate.instrument_id,
                            decision_at=observed_at,
                        )
                    except Exception as exc:
                        research_decision = None
                        reason_code = "RESEARCH_POLICY_RESOLUTION_ERROR"
                        detail = f"{type(exc).__name__}: {exc}"
                    else:
                        quality_gate = apply_research_policy_to_quality(
                            research_decision,
                            base_quality_score=result.features.quality_score,
                            minimum_quality_score=config.config.minimum_quality_score,
                        )
                        reason_code = quality_gate.reason_code
                        detail = None
                    allowed = quality_gate.allowed if research_decision is not None else False
                    if allowed and research_decision is not None and result.signal is not None:
                        adjusted_quality = quality_gate.adjusted_quality_score
                        result = result.model_copy(update={
                            "features": result.features.model_copy(update={"quality_score": adjusted_quality}),
                            "signal": result.signal.model_copy(update={"quality_score": adjusted_quality}),
                        })
                    payload = {
                        "strategy_version": config.config.strategy_version,
                        "policy_version": (
                            research_decision.policy_version if research_decision is not None else "trading-research-1"
                        ),
                        "authoritative": True,
                        "allowed": allowed,
                        "score_adjustment": (
                            quality_gate.score_adjustment if research_decision is not None else 0
                        ),
                        "base_quality_score": (
                            quality_gate.base_quality_score if research_decision is not None else result.features.quality_score
                        ),
                        "adjusted_quality_score": (
                            quality_gate.adjusted_quality_score if research_decision is not None else result.features.quality_score
                        ),
                        "minimum_quality_score": config.config.minimum_quality_score,
                        "detail": detail,
                        "decision_at": observed_at,
                    }
                    await self._event(
                        strategy_repository,
                        config,
                        instrument_id=candidate.instrument_id,
                        event_type="research_policy",
                        state="entry_ready" if allowed else "rejected",
                        reason_code=reason_code,
                        observed_at=observed_at,
                        payload=payload,
                    )
                    trade_log(
                        "auto_trading",
                        "research_policy_decision",
                        run_id=self.current_run_id,
                        strategy_id=config.strategy_id,
                        instrument_id=candidate.instrument_id,
                        **payload,
                        reason_code=reason_code,
                    )
                    if not allowed:
                        self.rejection_count += 1
                        continue
                proposals.append(
                    _EntryProposal(
                        candidate=candidate,
                        result=result,
                        observed_at=observed_at,
                    )
                )
        if learning_rows:
            ranked_learning = sorted(
                learning_rows,
                key=lambda row: (
                    -row[3].opportunity_score,
                    -row[3].execution_quality_score,
                    row[0].discovery_rank or 10**9,
                    row[0].instrument_id,
                ),
            )
            for rank, (candidate, result, observed_at, learning) in enumerate(ranked_learning, start=1):
                persisted = await self._event(
                    strategy_repository,
                    config,
                    instrument_id=candidate.instrument_id,
                    event_type="intraday_learning",
                    state=learning.pattern,
                    reason_code="INTRADAY_LEARNING_SNAPSHOT",
                    observed_at=observed_at,
                    payload={
                        "rank": rank,
                        "universe_id": universe.universe_id,
                        "universe_discovery_source": universe.discovery_source,
                        "morning_discovery_rank": candidate.discovery_rank,
                        "strategy_version": config.config.strategy_version,
                        "deterministic_state": result.state,
                        "deterministic_reason_code": result.reason_code,
                        "learning": learning.model_dump(mode="json"),
                        "research_only": True,
                        "execution_authority": False,
                    },
                )
                self.intraday_learning_snapshot_count += int(persisted)
            trade_log(
                "auto_trading",
                "intraday_learning_ranked",
                run_id=self.current_run_id,
                strategy_id=config.strategy_id,
                universe_id=universe.universe_id,
                candidate_count=len(ranked_learning),
                ranks=[
                    {
                        "instrument_id": row[0].instrument_id,
                        "rank": index,
                        "pattern": row[3].pattern,
                        "opportunity_score": row[3].opportunity_score,
                        "squeeze_probability_score": row[3].squeeze_probability_score,
                        "failed_selloff_probability_score": row[3].failed_selloff_probability_score,
                        "trend_continuation_score": row[3].trend_continuation_score,
                        "gap_retention_score": row[3].gap_retention_score,
                    }
                    for index, row in enumerate(ranked_learning, start=1)
                ],
                execution_authority=False,
            )

        proposals.sort(key=lambda proposal: proposal.priority)
        trade_log(
            "auto_trading",
            "candidate_arbitration",
            run_id=self.current_run_id,
            strategy_id=config.strategy_id,
            universe_id=universe.universe_id,
            proposal_count=len(proposals),
            proposals=[
                {
                    "instrument_id": proposal.candidate.instrument_id,
                    "observed_at": proposal.observed_at,
                    "quality_score": (
                        proposal.result.signal.quality_score
                        if proposal.result.signal is not None
                        else proposal.result.features.quality_score
                    ),
                    "discovery_rank": proposal.candidate.discovery_rank,
                    "priority": proposal.priority,
                }
                for proposal in proposals
            ],
        )
        return proposals

    async def _run_config(
        self,
        config: TradingStrategyConfigDocument,
        strategy_repository: TradingStrategyRepository,
        paper_repository: TradingPaperRepository,
        market_service: TradingMarketDataService,
    ) -> None:
        trade_log(
            "auto_trading",
            "strategy_cycle_start",
            run_id=self.current_run_id,
            strategy_id=config.strategy_id,
            account_id=config.account_id,
            strategy_kind=config.strategy_kind,
            strategy_version=config.strategy_version,
            mode=config.mode,
            enabled=config.enabled,
            active_universe_id=config.active_universe_id,
            config=config.config,
            risk_profile=config.risk,
        )
        await self._reconcile_protections(
            config,
            strategy_repository,
            paper_repository,
            market_service,
        )
        if config.mode == "off" or not config.enabled:
            trade_log(
                "auto_trading",
                "strategy_cycle_skipped",
                run_id=self.current_run_id,
                strategy_id=config.strategy_id,
                reason="mode_off" if config.mode == "off" else "disabled",
            )
            return

        now_utc = datetime.now(timezone.utc)
        if config.mode == "auto_paper" and config.config.strategy_version == "2.0.0":
            qualification_events = await asyncio.to_thread(
                _v2_qualification_events,
                strategy_repository,
                config.strategy_id,
                now=now_utc,
            )
            qualification = await asyncio.to_thread(
                evaluate_v2_prospective_qualification,
                config,
                qualification_events,
            )
            if not qualification.auto_paper_authorized:
                trade_log(
                    "auto_trading",
                    "v2_auto_paper_qualification_blocked",
                    run_id=self.current_run_id,
                    strategy_id=config.strategy_id,
                    profile_fingerprint=qualification.current_profile_fingerprint,
                    evidence_fingerprint=qualification.evidence_fingerprint,
                    reason_codes=qualification.reason_codes,
                    matched_eligible_trade_count=qualification.matched_eligible_trade_count,
                    execution_match_rate=qualification.execution_match_rate,
                    expectancy_r=qualification.expectancy_r,
                    one_sided_90_lcb_r=qualification.one_sided_90_lcb_r,
                    max_drawdown_r=qualification.max_drawdown_r,
                    execution_authority=False,
                )
                return
        now_et = now_utc.astimezone(_ET)
        today_et = now_et.date()
        day_start_et = datetime(today_et.year, today_et.month, today_et.day, tzinfo=_ET)
        day_end_et = day_start_et + timedelta(days=1)

        universe_source = "active_universe"
        if config.active_universe_id is not None:
            universe = await asyncio.to_thread(
                strategy_repository.get_universe,
                config.active_universe_id,
            )
        else:
            universe = await asyncio.to_thread(
                resolve_v2_shadow_archive,
                config,
                strategy_repository,
                now=now_utc,
            )
            universe_source = "auto_archive_shadow"
            if universe is None:
                trade_log(
                    "auto_trading",
                    "strategy_cycle_skipped",
                    run_id=self.current_run_id,
                    strategy_id=config.strategy_id,
                    reason=(
                        "v2_shadow_archive_not_ready"
                        if config.mode == "shadow" and config.config.strategy_version == "2.0.0"
                        else "no_active_universe"
                    ),
                )
                return

        trade_log(
            "auto_trading",
            "universe_loaded",
            run_id=self.current_run_id,
            strategy_id=config.strategy_id,
            universe_id=universe.universe_id,
            runtime_universe_source=universe_source,
            session_date=universe.session_date,
            evaluation_time=universe.evaluation_time,
            discovery_source=universe.discovery_source,
            source_fingerprint=universe.source_fingerprint,
            candidate_count=len(universe.candidates),
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
        if config.mode == "shadow" and proposals:
            for proposal in proposals:
                candidate = proposal.candidate
                result = proposal.result
                assert result.signal is not None
                try:
                    evidence = await asyncio.to_thread(
                        observe_shadow_execution,
                        market_service,
                        instrument_id=candidate.instrument_id,
                        binding_id=candidate.binding_id,
                    )
                except Exception as exc:
                    payload = {
                        "strategy_version": config.config.strategy_version,
                        "mode": "shadow",
                        "universe_id": universe.universe_id,
                        "universe_source": universe_source,
                        "profile_fingerprint": (
                            v2_profile_fingerprint(config.config)
                            if config.config.strategy_version == "2.0.0"
                            else None
                        ),
                        "signal": result.signal.model_dump(mode="json"),
                        "features": result.features.model_dump(mode="json"),
                        "error_type": type(exc).__name__,
                        "detail": str(exc),
                        "execution_authority": False,
                    }
                    await self._event(
                        strategy_repository,
                        config,
                        instrument_id=candidate.instrument_id,
                        event_type="shadow_execution",
                        state=result.state,
                        reason_code="SHADOW_EXECUTION_UNAVAILABLE",
                        observed_at=proposal.observed_at,
                        payload=payload,
                    )
                    trade_log(
                        "auto_trading",
                        "shadow_execution_unavailable",
                        run_id=self.current_run_id,
                        strategy_id=config.strategy_id,
                        instrument_id=candidate.instrument_id,
                        **payload,
                    )
                    continue

                payload = {
                    "strategy_version": config.config.strategy_version,
                    "mode": "shadow",
                    "universe_id": universe.universe_id,
                    "universe_source": universe_source,
                    "profile_fingerprint": (
                        v2_profile_fingerprint(config.config)
                        if config.config.strategy_version == "2.0.0"
                        else None
                    ),
                    "signal": result.signal.model_dump(mode="json"),
                    "features": result.features.model_dump(mode="json"),
                    "execution": evidence.execution,
                    "execution_authority": False,
                }
                await self._event(
                    strategy_repository,
                    config,
                    instrument_id=candidate.instrument_id,
                    event_type="shadow_execution",
                    state=result.state,
                    reason_code=evidence.reason_code,
                    observed_at=proposal.observed_at,
                    payload=payload,
                )
                trade_log(
                    "auto_trading",
                    "shadow_execution_observation",
                    run_id=self.current_run_id,
                    strategy_id=config.strategy_id,
                    instrument_id=candidate.instrument_id,
                    reason_code=evidence.reason_code,
                    **payload,
                )

            trade_log(
                "auto_trading",
                "strategy_cycle_no_entry_work",
                run_id=self.current_run_id,
                strategy_id=config.strategy_id,
                mode=config.mode,
                proposal_count=len(proposals),
                shadow_execution_observed=True,
            )
            return

        if config.mode != "auto_paper" or not proposals:
            trade_log(
                "auto_trading",
                "strategy_cycle_no_entry_work",
                run_id=self.current_run_id,
                strategy_id=config.strategy_id,
                mode=config.mode,
                proposal_count=len(proposals),
            )
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
        submitted_attempts = {
            str(event.payload.get("trade_attempt_id"))
            if event.payload.get("trade_attempt_id")
            else _trade_attempt_id(config.strategy_id, event.instrument_id, event.observed_at)
            for event in entry_events
        }

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
        positions_by_instrument = {position.instrument_id: position for position in snapshot.positions}
        open_risk = Decimal("0")
        for item in protections:
            if item.status not in {"pending_entry", "active"}:
                continue
            position = positions_by_instrument.get(item.instrument_id)
            if (
                config.config.strategy_version == "2.0.0"
                and item.status == "active"
                and position is not None
            ):
                # After V2 profit protection moves above entry, remaining downside
                # risk is zero rather than the old target/stop geometric estimate.
                per_share_risk = max(Decimal("0"), position.average_cost - item.stop_price)
            else:
                per_share_risk = max(
                    Decimal("0"),
                    (item.target_price - item.stop_price)
                    / (config.config.reward_multiple + Decimal("1")),
                )
            open_risk += item.quantity * per_share_risk
        trade_log(
            "auto_trading",
            "portfolio_risk_context",
            run_id=self.current_run_id,
            strategy_id=config.strategy_id,
            account_id=config.account_id,
            trades_today=trades_today,
            traded_symbols=sorted(traded_symbols),
            submitted_attempts=sorted(submitted_attempts),
            protected_symbols=sorted(protected_symbols),
            daily_realized_pnl=daily_realized_pnl,
            open_strategy_risk=open_risk,
            balances=[balance.model_dump(mode="json") for balance in snapshot.balances],
            positions=[position.model_dump(mode="json") for position in snapshot.positions],
            open_orders=[order.model_dump(mode="json") for order in snapshot.open_orders],
        )

        for proposal in proposals:
            candidate = proposal.candidate
            result = proposal.result
            assert result.signal is not None
            observed_at = proposal.observed_at
            trade_attempt_id = _trade_attempt_id(
                config.strategy_id,
                candidate.instrument_id,
                observed_at,
            )
            if trade_attempt_id in submitted_attempts:
                trade_log(
                    "auto_trading",
                    "candidate_skipped",
                    run_id=self.current_run_id,
                    strategy_id=config.strategy_id,
                    instrument_id=candidate.instrument_id,
                    trade_attempt_id=trade_attempt_id,
                    reason="trade_attempt_already_submitted",
                )
                continue
            if candidate.instrument_id in protected_symbols:
                trade_log(
                    "auto_trading",
                    "candidate_skipped",
                    run_id=self.current_run_id,
                    strategy_id=config.strategy_id,
                    instrument_id=candidate.instrument_id,
                    reason="existing_strategy_protection",
                )
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
                    payload={"detail": str(exc), "trade_attempt_id": trade_attempt_id},
                )
                trade_log(
                    "auto_trading",
                    "execution_observation_error",
                    run_id=self.current_run_id,
                    strategy_id=config.strategy_id,
                    instrument_id=candidate.instrument_id,
                    trade_attempt_id=trade_attempt_id,
                    error_type=type(exc).__name__,
                    detail=str(exc),
                )
                continue
            execution_payload = _execution_audit_payload(execution)
            trade_log(
                "auto_trading",
                "execution_observation",
                run_id=self.current_run_id,
                strategy_id=config.strategy_id,
                instrument_id=candidate.instrument_id,
                trade_attempt_id=trade_attempt_id,
                signal=result.signal,
                execution=execution_payload,
            )
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
                    payload={
                        "trade_attempt_id": trade_attempt_id,
                        "reasons": list(execution.rejection_reasons),
                        "execution": execution_payload,
                    },
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
            decision_payload = decision.model_dump(mode="json")
            profile_fingerprint = (
                v2_profile_fingerprint(config.config)
                if config.config.strategy_version == "2.0.0"
                else config.config.strategy_version
            )
            risk_event_payload = {
                "trade_attempt_id": trade_attempt_id,
                "strategy_version": config.config.strategy_version,
                "profile_fingerprint": profile_fingerprint,
                "universe_id": universe.universe_id,
                "risk_decision": decision_payload,
                "execution": execution_payload,
                "signal": result.signal.model_dump(mode="json"),
                "features": result.features.model_dump(mode="json"),
                "trades_today_before_entry": trades_today,
                "daily_realized_pnl": (
                    str(daily_realized_pnl) if daily_realized_pnl is not None else None
                ),
                "open_strategy_risk_before_entry": str(open_risk),
            }
            await self._event(
                strategy_repository,
                config,
                instrument_id=candidate.instrument_id,
                event_type="risk_decision",
                state="approved" if decision.allowed else "rejected",
                reason_code=decision.reason_code,
                observed_at=observed_at,
                payload=risk_event_payload,
            )
            trade_log(
                "auto_trading",
                "risk_decision",
                run_id=self.current_run_id,
                strategy_id=config.strategy_id,
                account_id=config.account_id,
                instrument_id=candidate.instrument_id,
                trade_attempt_id=trade_attempt_id,
                observed_at=observed_at,
                trades_today=trades_today,
                daily_realized_pnl=daily_realized_pnl,
                open_strategy_risk=open_risk,
                spread_bps=execution.spread_bps,
                signal=result.signal,
                decision=decision_payload,
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
                    payload={
                        **decision_payload,
                        "trade_attempt_id": trade_attempt_id,
                        "execution": execution_payload,
                        "signal": result.signal.model_dump(mode="json"),
                    },
                )
                continue

            order_key = _key(config.strategy_id, trade_attempt_id, "entry")
            order_id = f"strat-{order_key[:32]}"
            protection = StrategyProtection(
                strategy_id=config.strategy_id,
                protection_id=f"prot-{order_key[:32]}",
                account_id=config.account_id,
                instrument_id=candidate.instrument_id,
                entry_order_id=order_id,
                stop_price=result.signal.stop_price,
                target_price=result.signal.target_price,
                initial_stop_price=result.signal.stop_price,
                initial_target_price=(
                    None if config.config.strategy_version == "2.0.0"
                    else result.signal.target_price
                ),
                quantity=decision.quantity,
                status="pending_entry",
            )
            # Arm protection before the order can become executable. The strategy
            # protection table intentionally does not require the paper order FK,
            # so a crash between these writes is fail-closed rather than exposed.
            await asyncio.to_thread(strategy_repository.save_protection, protection)
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
                protection.status = "cancelled"
                protection.trigger_reason = "entry_submit_failed"
                try:
                    await asyncio.to_thread(strategy_repository.save_protection, protection)
                except ValueError as cleanup_exc:
                    self.last_error = f"entry_protection_cleanup: {cleanup_exc}"
                self.rejection_count += 1
                await self._event(
                    strategy_repository,
                    config,
                    instrument_id=candidate.instrument_id,
                    event_type="rejection",
                    state=result.state,
                    reason_code="PAPER_ORDER_REJECTED",
                    observed_at=observed_at,
                    payload={
                        "detail": str(exc),
                        "trade_attempt_id": trade_attempt_id,
                        "order_id": order_id,
                        "execution": execution_payload,
                        "risk_decision": decision_payload,
                        "signal": result.signal.model_dump(mode="json"),
                    },
                )
                trade_log(
                    "auto_trading",
                    "entry_order_rejected",
                    run_id=self.current_run_id,
                    strategy_id=config.strategy_id,
                    account_id=config.account_id,
                    instrument_id=candidate.instrument_id,
                    trade_attempt_id=trade_attempt_id,
                    order_id=order_id,
                    detail=str(exc),
                    execution=execution_payload,
                    risk_decision=decision_payload,
                )
                continue

            await self._event(
                strategy_repository,
                config,
                instrument_id=candidate.instrument_id,
                event_type="entry_order_submitted",
                state="entry_ready",
                reason_code="AUTO_PAPER_ENTRY_SUBMITTED",
                observed_at=observed_at,
                payload={
                    "trade_attempt_id": trade_attempt_id,
                    "strategy_version": config.config.strategy_version,
                    "profile_fingerprint": profile_fingerprint,
                    "order_id": order_id,
                    "quantity": str(decision.quantity),
                    "reference_price": str(execution.ask or execution.last),
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
                    "signal": result.signal.model_dump(mode="json"),
                    "features": result.features.model_dump(mode="json"),
                    "execution": execution_payload,
                    "risk_decision": decision_payload,
                    "trades_today_before_entry": trades_today,
                    "daily_realized_pnl": str(daily_realized_pnl) if daily_realized_pnl is not None else None,
                    "open_strategy_risk_before_entry": str(open_risk),
                    "universe_id": universe.universe_id,
                },
            )
            trade_log(
                "auto_trading",
                "entry_order_submitted",
                run_id=self.current_run_id,
                strategy_id=config.strategy_id,
                account_id=config.account_id,
                instrument_id=candidate.instrument_id,
                trade_attempt_id=trade_attempt_id,
                order_id=order_id,
                quantity=decision.quantity,
                reference_price=execution.ask or execution.last,
                signal=result.signal,
                features=result.features,
                execution=execution_payload,
                risk_decision=decision_payload,
            )
            self.paper_order_count += 1
            trades_today += 1
            traded_symbols.add(candidate.instrument_id)
            submitted_attempts.add(trade_attempt_id)
            protected_symbols.add(candidate.instrument_id)
            open_risk += decision.estimated_risk

    async def run_once(self) -> int:
        strategy_repository = self.strategy_repository_factory()
        paper_repository = self.paper_repository_factory()
        market_service = self.market_service_factory()
        configs = await asyncio.to_thread(strategy_repository.list_configs, active_only=True)
        before = self.paper_order_count
        started_at = datetime.now(timezone.utc)
        self.current_run_id = _run_id("auto", started_at)
        trade_log(
            "auto_trading",
            "monitor_run_start",
            run_id=self.current_run_id,
            started_at=started_at,
            active_strategy_count=len(configs),
            interval_seconds=self.interval_seconds,
            evaluation_count_before=self.evaluation_count,
            signal_count_before=self.signal_count,
            paper_order_count_before=self.paper_order_count,
            rejection_count_before=self.rejection_count,
        )
        try:
            for config in configs:
                try:
                    await self._run_config(config, strategy_repository, paper_repository, market_service)
                except Exception as exc:
                    self.last_error = f"{config.strategy_id}: {type(exc).__name__}: {exc}"
                    trade_log(
                        "auto_trading",
                        "strategy_cycle_error",
                        run_id=self.current_run_id,
                        strategy_id=config.strategy_id,
                        error_type=type(exc).__name__,
                        detail=str(exc),
                    )
            self.last_run_at = datetime.now(timezone.utc)
            new_orders = self.paper_order_count - before
            trade_log(
                "auto_trading",
                "monitor_run_complete",
                run_id=self.current_run_id,
                started_at=started_at,
                completed_at=self.last_run_at,
                new_paper_orders=new_orders,
                last_error=self.last_error,
                evaluation_count=self.evaluation_count,
                signal_count=self.signal_count,
                paper_order_count=self.paper_order_count,
                rejection_count=self.rejection_count,
            )
            return new_orders
        finally:
            self.current_run_id = None

    def diagnostics(self) -> dict[str, Any]:
        return {
            "enabled": trading_strategy_monitor_enabled(),
            "running": self._task is not None,
            "interval_seconds": self.interval_seconds,
            "current_run_id": self.current_run_id,
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
                trade_log(
                    "auto_trading",
                    "monitor_loop_error",
                    run_id=self.current_run_id,
                    error_type=type(exc).__name__,
                    detail=str(exc),
                )
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
