from __future__ import annotations

import asyncio
import hashlib
import os
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
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
from .strategy_data_integrity import assess_universe_integrity
from .strategy_intraday_learning import IntradayLearningSnapshot, build_intraday_learning_snapshot
from .strategy_managed_finviz_shadow import (
    managed_finviz_shadow_autoprovision_enabled,
    provision_managed_finviz_shadow_strategy,
)
from .strategy_intraday_llm import (
    EVENT_BATCH_COOLDOWN_MINUTES,
    FULL_REFRESH_MINUTES,
    IntradayLLMAnalyzer,
    select_intraday_llm_candidates,
    should_run_intraday_llm_batch,
)
from .strategy_research_policy import apply_research_policy_to_quality, resolve_strategy_research_policy
from .strategy_risk import size_strategy_entry
from .strategy_shadow_execution import observe_shadow_execution
from .strategy_shadow_universe import resolve_v2_runtime_archive
from .strategy_stoch_execution_cost import (
    StochExecutionAction,
    action_for_snapshot as stoch_execution_action_for_snapshot,
    build_execution_summary as build_stoch_execution_summary,
    requested_fraction_for_action as stoch_requested_fraction_for_action,
    simulate_stoch_execution,
)
from .strategy_stoch_trend_capture import (
    evaluate_stoch_trend_capture,
    stoch_trend_capture_risk_decision,
)
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
_REGULAR_OPEN = time(9, 30)
_DIAGNOSTIC_LOG_INTERVAL = timedelta(minutes=5)


def _finalized_bars_for_session(bars, session_date: date):
    return sorted(
        (
            bar
            for bar in bars
            if bar.is_final
            and bar.start_time.astimezone(_ET).date() == session_date
        ),
        key=lambda bar: bar.start_time,
    )


def _current_session_1m_integrity(
    bars,
    *,
    session_date: date,
    observed_at: datetime,
) -> tuple[bool, str]:
    observed_et = observed_at.astimezone(_ET)
    if observed_et.date() < session_date or (
        observed_et.date() == session_date and observed_et.time() < _REGULAR_OPEN
    ):
        return False, "CURRENT_SESSION_NOT_STARTED"
    regular = [
        bar
        for bar in bars
        if _REGULAR_OPEN <= bar.start_time.astimezone(_ET).time() < time(16, 0)
    ]
    if not regular:
        return False, "CURRENT_SESSION_1M_UNAVAILABLE"
    first = regular[0].start_time.astimezone(_ET)
    if first.time() > _REGULAR_OPEN:
        return False, "OPENING_1M_HISTORY_INCOMPLETE"
    return True, "CURRENT_SESSION_1M_READY"


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
    "DATA_INCOMPLETE",
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
        intraday_llm_analyzer_factory: Callable[[], IntradayLLMAnalyzer] = IntradayLLMAnalyzer,
        interval_seconds: float | None = None,
    ) -> None:
        self.strategy_repository_factory = strategy_repository_factory
        self.paper_repository_factory = paper_repository_factory
        self.market_service_factory = market_service_factory
        self.intraday_llm_analyzer_factory = intraday_llm_analyzer_factory
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
        self.intraday_llm_call_count = 0
        self.intraday_llm_assessment_count = 0
        self.intraday_llm_error_count = 0
        self.intraday_llm_input_character_count = 0
        self.intraday_llm_input_token_count = 0
        self.intraday_llm_output_token_count = 0
        self.intraday_llm_total_token_count = 0
        self.intraday_llm_estimated_usage_count = 0
        self._last_evaluated_bar_end: dict[tuple[str, str, str], datetime] = {}
        self._last_diagnostic_log_at: dict[tuple[str, ...], datetime] = {}
        self.managed_finviz_shadow_provision: dict[str, object] | None = None
        self.managed_finviz_shadow_provision_error: str | None = None

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

    def _should_log_diagnostic(
        self,
        key: tuple[str, ...],
        observed_at: datetime,
    ) -> bool:
        previous = self._last_diagnostic_log_at.get(key)
        if previous is not None and observed_at < previous + _DIAGNOSTIC_LOG_INTERVAL:
            return False
        self._last_diagnostic_log_at[key] = observed_at
        return True

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

    async def _run_intraday_llm(
        self,
        config: TradingStrategyConfigDocument,
        strategy_repository: TradingStrategyRepository,
        universe,
        ranked_learning: list[tuple[GapperCandidate, GapPullbackResult, datetime, IntradayLearningSnapshot]],
    ) -> None:
        if not config.config.intraday_llm_enabled or not ranked_learning:
            return

        observed_at = max(row[2] for row in ranked_learning)
        if observed_at.astimezone(_ET).date() != universe.session_date:
            trade_log(
                "auto_trading",
                "intraday_llm_skipped",
                run_id=self.current_run_id,
                strategy_id=config.strategy_id,
                universe_id=universe.universe_id,
                reason="bar_session_mismatch",
                observed_at=observed_at,
                universe_session_date=universe.session_date,
                research_only=True,
                execution_authority=False,
            )
            return
        if hasattr(strategy_repository, "events_by_types_between"):
            session_start_et = datetime(
                universe.session_date.year,
                universe.session_date.month,
                universe.session_date.day,
                tzinfo=_ET,
            )
            recent_events = list(
                reversed(
                    await asyncio.to_thread(
                        strategy_repository.events_by_types_between,
                        config.strategy_id,
                        event_types=("intraday_llm", "intraday_llm_batch"),
                        start_time=session_start_et.astimezone(timezone.utc),
                        end_time=observed_at.astimezone(timezone.utc) + timedelta(seconds=1),
                        limit=5_000,
                    )
                )
            )
        else:
            recent_events = await asyncio.to_thread(
                strategy_repository.recent_events,
                config.strategy_id,
                2_000,
            )
        previous_by_instrument: dict[str, dict[str, Any]] = {}
        previous_observed_at_by_instrument: dict[str, datetime] = {}
        last_full_refresh_at_by_instrument: dict[str, datetime] = {}
        previous_batch_at: datetime | None = None
        for event in recent_events:
            payload = event.payload if isinstance(event.payload, dict) else {}
            if payload.get("universe_id") != universe.universe_id:
                continue
            if event.event_type == "intraday_llm_batch" and previous_batch_at is None:
                previous_batch_at = event.observed_at
            if event.event_type != "intraday_llm":
                continue
            if event.instrument_id not in previous_by_instrument:
                previous_by_instrument[event.instrument_id] = payload
                previous_observed_at_by_instrument[event.instrument_id] = event.observed_at
            if (
                payload.get("payload_mode") == "full"
                and event.instrument_id not in last_full_refresh_at_by_instrument
            ):
                last_full_refresh_at_by_instrument[event.instrument_id] = event.observed_at

        observed_et = observed_at.astimezone(_ET).time()
        heartbeat_enabled = (
            config.config.entry_start_et <= observed_et <= config.config.last_entry_et
        )
        selected, trigger_reasons = select_intraday_llm_candidates(
            ranked_learning,
            top_n=config.config.intraday_llm_top_n,
            previous_by_instrument=previous_by_instrument,
            previous_observed_at_by_instrument=previous_observed_at_by_instrument,
            heartbeat_minutes=config.config.intraday_llm_interval_minutes,
            heartbeat_enabled=heartbeat_enabled,
        )
        if not selected:
            return

        urgent_entry_ready = any(
            "entry_ready" in trigger_reasons.get(row[0].instrument_id, ())
            for row in selected
        )
        if (
            not urgent_entry_ready
            and not should_run_intraday_llm_batch(
                observed_at=observed_at,
                previous_batch_at=previous_batch_at,
                minimum_interval_minutes=EVENT_BATCH_COOLDOWN_MINUTES,
            )
        ):
            return

        ranks = {
            row[0].instrument_id: rank
            for rank, row in enumerate(ranked_learning, start=1)
        }
        payload_modes: dict[str, str] = {}
        for candidate, _, row_observed_at, _ in selected:
            instrument_id = candidate.instrument_id
            previous = previous_by_instrument.get(instrument_id)
            last_full = last_full_refresh_at_by_instrument.get(instrument_id)
            payload_modes[instrument_id] = (
                "full"
                if previous is None
                or last_full is None
                or row_observed_at >= last_full + timedelta(minutes=FULL_REFRESH_MINUTES)
                else "delta"
            )

        analyzer = self.intraday_llm_analyzer_factory()
        self.intraday_llm_call_count += 1
        try:
            result = await asyncio.to_thread(
                analyzer.assess,
                selected,
                ranks=ranks,
                previous_by_instrument=previous_by_instrument,
                trigger_reasons_by_instrument=trigger_reasons,
                payload_modes_by_instrument=payload_modes,
            )
        except Exception as exc:
            self.intraday_llm_error_count += 1
            trade_log(
                "auto_trading",
                "intraday_llm_error",
                run_id=self.current_run_id,
                strategy_id=config.strategy_id,
                universe_id=universe.universe_id,
                error_type=type(exc).__name__,
                detail=str(exc),
                trigger_reasons=trigger_reasons,
                research_only=True,
                execution_authority=False,
            )
            # A failed event-driven batch is still a short cooldown checkpoint so
            # a temporarily unavailable default provider is not hammered every
            # monitor poll. ENTRY_READY can bypass this cooldown on a new state
            # transition.
            await self._event(
                strategy_repository,
                config,
                instrument_id="__universe__",
                event_type="intraday_llm_batch",
                state="error",
                reason_code="INTRADAY_LLM_BATCH_ERROR",
                observed_at=observed_at,
                payload={
                    "universe_id": universe.universe_id,
                    "error_type": type(exc).__name__,
                    "detail": str(exc),
                    "requested_instrument_ids": [row[0].instrument_id for row in selected],
                    "trigger_reasons": trigger_reasons,
                    "heartbeat_enabled": heartbeat_enabled,
                    "event_cooldown_minutes": EVENT_BATCH_COOLDOWN_MINUTES,
                    "research_only": True,
                    "execution_authority": False,
                },
            )
            return

        selected_by_id = {row[0].instrument_id: row for row in selected}
        for assessment in result.assessments:
            row = selected_by_id.get(assessment.instrument_id)
            if row is None:
                continue
            candidate, deterministic, row_observed_at, learning = row
            persisted = await self._event(
                strategy_repository,
                config,
                instrument_id=assessment.instrument_id,
                event_type="intraday_llm",
                state=assessment.market_regime,
                reason_code="INTRADAY_LLM_ASSESSMENT",
                observed_at=row_observed_at,
                payload={
                    "universe_id": universe.universe_id,
                    "universe_discovery_source": universe.discovery_source,
                    "morning_discovery_rank": candidate.discovery_rank,
                    "live_research_rank": ranks.get(assessment.instrument_id),
                    "provider": result.provider,
                    "model": result.model,
                    "trigger_reasons": list(
                        trigger_reasons.get(assessment.instrument_id, ())
                    ),
                    "payload_mode": payload_modes.get(assessment.instrument_id, "delta"),
                    "deterministic_state": deterministic.state,
                    "deterministic_reason_code": deterministic.reason_code,
                    # Persist full causal state for future delta construction even
                    # when only a compact delta was sent to the provider.
                    "source_learning": learning.model_dump(mode="json"),
                    "assessment": assessment.model_dump(mode="json"),
                    "research_only": True,
                    "execution_authority": False,
                },
            )
            self.intraday_llm_assessment_count += int(persisted)

        self.intraday_llm_input_character_count += result.input_characters
        self.intraday_llm_input_token_count += result.input_tokens
        self.intraday_llm_output_token_count += result.output_tokens
        self.intraday_llm_total_token_count += result.total_tokens
        if result.usage_source == "estimated":
            self.intraday_llm_estimated_usage_count += 1
        await self._event(
            strategy_repository,
            config,
            instrument_id="__universe__",
            event_type="intraday_llm_batch",
            state="completed",
            reason_code="INTRADAY_LLM_BATCH_COMPLETED",
            observed_at=observed_at,
            payload={
                "universe_id": universe.universe_id,
                "provider": result.provider,
                "model": result.model,
                "requested_instrument_ids": [row[0].instrument_id for row in selected],
                "assessment_count": len(result.assessments),
                "top_n": config.config.intraday_llm_top_n,
                "heartbeat_minutes": config.config.intraday_llm_interval_minutes,
                "heartbeat_enabled": heartbeat_enabled,
                "event_cooldown_minutes": EVENT_BATCH_COOLDOWN_MINUTES,
                "full_refresh_minutes": FULL_REFRESH_MINUTES,
                "trigger_reasons": trigger_reasons,
                "payload_modes": payload_modes,
                "token_usage": {
                    "source": result.usage_source,
                    "input_characters": result.input_characters,
                    "output_characters": result.output_characters,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "total_tokens": result.total_tokens,
                },
                "research_only": True,
                "execution_authority": False,
            },
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
        evaluated_any = False

        captured_stoch_entry_signals: set[tuple[str, str]] = set()
        captured_stoch_execution_actions: set[tuple[str, str, str]] = set()
        stoch_entry_payload_by_instrument: dict[str, dict[str, object]] = {}
        stoch_action_payloads_by_instrument: dict[
            str,
            dict[StochExecutionAction, dict[str, object]],
        ] = {}
        stoch_execution_history_available = True
        if config.config.stoch_trend_capture_enabled:
            session_start_et = datetime(
                universe.session_date.year,
                universe.session_date.month,
                universe.session_date.day,
                tzinfo=_ET,
            )
            session_end_et = session_start_et + timedelta(days=1)
            try:
                if hasattr(strategy_repository, "events_by_types_between"):
                    prior_stoch_events = await asyncio.to_thread(
                        strategy_repository.events_by_types_between,
                        config.strategy_id,
                        event_types=(
                            "stoch_trend_capture_entry",
                            "stoch_trend_execution",
                        ),
                        start_time=session_start_et.astimezone(timezone.utc),
                        end_time=session_end_et.astimezone(timezone.utc),
                        limit=2_000,
                    )
                else:
                    prior_stoch_events = [
                        event
                        for event in await asyncio.to_thread(
                            strategy_repository.recent_events,
                            config.strategy_id,
                            4_000,
                        )
                        if event.event_type
                        in {
                            "stoch_trend_capture_entry",
                            "stoch_trend_execution",
                        }
                        and session_start_et.astimezone(timezone.utc)
                        <= event.observed_at.astimezone(timezone.utc)
                        < session_end_et.astimezone(timezone.utc)
                    ]

                for event in prior_stoch_events:
                    payload = event.payload if isinstance(event.payload, dict) else {}
                    if event.event_type == "stoch_trend_capture_entry":
                        captured_stoch_entry_signals.add(
                            (
                                event.instrument_id,
                                event.observed_at.astimezone(timezone.utc).isoformat(),
                            )
                        )
                        stoch_entry_payload_by_instrument[event.instrument_id] = payload
                        continue

                    action = payload.get("action")
                    if action not in {
                        "range_exit",
                        "partial_exit",
                        "runner_exit",
                        "force_flat",
                    }:
                        continue
                    action_name = str(action)
                    captured_stoch_execution_actions.add(
                        (
                            event.instrument_id,
                            action_name,
                            event.observed_at.astimezone(timezone.utc).isoformat(),
                        )
                    )
                    stoch_action_payloads_by_instrument.setdefault(
                        event.instrument_id,
                        {},
                    )[action_name] = payload  # type: ignore[index]
            except Exception as exc:
                stoch_execution_history_available = False
                # Evidence lookup is fail-closed for the overlay only. The
                # canonical deterministic strategy continues unaffected.
                trade_log(
                    "auto_trading",
                    "stoch_trend_execution_history_error",
                    run_id=self.current_run_id,
                    strategy_id=config.strategy_id,
                    universe_id=universe.universe_id,
                    error_type=type(exc).__name__,
                    detail=str(exc),
                    research_only=True,
                    execution_authority=False,
                )

        for candidate in universe.candidates:
            now_utc = datetime.now(timezone.utc)
            integrity_observed_at = getattr(universe, "evaluation_time", now_utc)
            legacy_candidate_contract = not hasattr(
                universe, "evaluation_time"
            ) and not hasattr(candidate, "market_data_complete")
            if getattr(candidate, "market_data_complete", True) is False:
                await self._event(
                    strategy_repository,
                    config,
                    instrument_id=candidate.instrument_id,
                    event_type="data_integrity",
                    state="invalid",
                    reason_code="DATA_INCOMPLETE",
                    observed_at=integrity_observed_at,
                    payload={
                        "universe_id": universe.universe_id,
                        "market_data_complete": False,
                        "data_quality_flags": list(
                            getattr(candidate, "data_quality_flags", ())
                        ),
                        "premarket_bar_count": getattr(
                            candidate,
                            "premarket_bar_count",
                            None,
                        ),
                        "causal_1m_available": False,
                        "research_only": True,
                        "execution_authority": False,
                    },
                )
                continue

            primary_error: Exception | None = None
            stoch_capture = None
            try:
                response = await asyncio.to_thread(
                    market_service.bars,
                    candidate.instrument_id,
                    "1m",
                    500,
                    candidate.binding_id,
                )
                if legacy_candidate_contract:
                    base_bars = [bar for bar in response.bars if bar.is_final]
                else:
                    base_bars = _finalized_bars_for_session(
                        response.bars,
                        universe.session_date,
                    )
            except Exception as exc:
                primary_error = exc
                base_bars = []

            if legacy_candidate_contract:
                current_ready = bool(base_bars)
                integrity_reason = (
                    "CURRENT_SESSION_1M_READY"
                    if current_ready
                    else "CURRENT_SESSION_1M_UNAVAILABLE"
                )
            else:
                current_ready, integrity_reason = _current_session_1m_integrity(
                    base_bars,
                    session_date=universe.session_date,
                    observed_at=now_utc,
                )
            bar_source = "configured_history"

            # Finviz learning is a non-canonical SHADOW experiment. It may use
            # current Alpaca IEX indicator history to rescue a missing Yahoo
            # opening sequence, but canonical AUTO PAPER never changes evidence
            # source through this path.
            if (
                not current_ready
                and integrity_reason != "CURRENT_SESSION_NOT_STARTED"
                and config.mode == "shadow"
                and universe.discovery_source == "finviz"
            ):
                try:
                    fallback_bars = await asyncio.to_thread(
                        market_service.execution_indicator_bars,
                        candidate.instrument_id,
                        candidate.binding_id,
                        as_of=now_utc,
                    )
                    fallback_session = _finalized_bars_for_session(
                        fallback_bars,
                        universe.session_date,
                    )
                    fallback_ready, fallback_reason = _current_session_1m_integrity(
                        fallback_session,
                        session_date=universe.session_date,
                        observed_at=now_utc,
                    )
                except Exception as fallback_exc:
                    fallback_ready = False
                    fallback_reason = integrity_reason
                    if self._should_log_diagnostic(
                        ("bars_fallback", config.strategy_id, candidate.instrument_id),
                        now_utc,
                    ):
                        trade_log(
                            "auto_trading",
                            "candidate_bars_fallback_error",
                            run_id=self.current_run_id,
                            strategy_id=config.strategy_id,
                            universe_id=universe.universe_id,
                            instrument_id=candidate.instrument_id,
                            error_type=type(fallback_exc).__name__,
                            detail=str(fallback_exc),
                            execution_authority=False,
                        )
                if fallback_ready:
                    base_bars = fallback_session
                    current_ready = True
                    integrity_reason = "CURRENT_SESSION_1M_FALLBACK"
                    bar_source = "alpaca_iex_indicator_fallback"
                else:
                    integrity_reason = fallback_reason

            if not current_ready:
                state = "waiting" if integrity_reason == "CURRENT_SESSION_NOT_STARTED" else "invalid"
                await self._event(
                    strategy_repository,
                    config,
                    instrument_id=candidate.instrument_id,
                    event_type="data_integrity",
                    state=state,
                    reason_code=integrity_reason,
                    observed_at=integrity_observed_at,
                    payload={
                        "universe_id": universe.universe_id,
                        "market_data_complete": True,
                        "current_session_1m_complete": False,
                        "causal_1m_available": False,
                        "detected_at": now_utc,
                        "primary_error": (
                            f"{type(primary_error).__name__}: {primary_error}"
                            if primary_error is not None
                            else None
                        ),
                        "research_only": True,
                        "execution_authority": False,
                    },
                )
                if primary_error is not None and self._should_log_diagnostic(
                    ("bars_primary", config.strategy_id, candidate.instrument_id),
                    now_utc,
                ):
                    self.last_error = (
                        f"strategy_bars: {type(primary_error).__name__}: {primary_error}"
                    )
                    trade_log(
                        "auto_trading",
                        "candidate_bars_error",
                        run_id=self.current_run_id,
                        strategy_id=config.strategy_id,
                        universe_id=universe.universe_id,
                        instrument_id=candidate.instrument_id,
                        binding_id=candidate.binding_id,
                        error_type=type(primary_error).__name__,
                        detail=str(primary_error),
                    )
                continue

            execution_bars = resample_final_bars(
                base_bars,
                config.config.execution_interval,
            )
            structure_bars = resample_final_bars(
                base_bars,
                config.config.structure_interval,
            )
            if not execution_bars or not structure_bars:
                if self._should_log_diagnostic(
                    ("bars_unusable", config.strategy_id, candidate.instrument_id),
                    now_utc,
                ):
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

            evaluation_key = (
                config.strategy_id,
                universe.universe_id,
                candidate.instrument_id,
            )
            latest_bar_end = base_bars[-1].end_time
            if (
                not legacy_candidate_contract
                and self._last_evaluated_bar_end.get(evaluation_key) == latest_bar_end
            ):
                continue
            self._last_evaluated_bar_end[evaluation_key] = latest_bar_end

            result = evaluate_gap_pullback(candidate, structure_bars, config.config)
            observed_at = structure_bars[-1].end_time
            evaluated_any = True
            self.evaluation_count += 1
            await self._event(
                strategy_repository,
                config,
                instrument_id=candidate.instrument_id,
                event_type="data_integrity",
                state="valid",
                reason_code=integrity_reason,
                observed_at=integrity_observed_at,
                payload={
                    "universe_id": universe.universe_id,
                    "market_data_complete": True,
                    "current_session_1m_complete": True,
                    "causal_1m_available": True,
                    "bar_source": bar_source,
                    "detected_at": now_utc,
                    "research_only": True,
                    "execution_authority": False,
                },
            )
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
                    "current_session_1m_complete": True,
                    "causal_1m_available": True,
                    "bar_source": bar_source,
                    "latest_structure_bar": _bar_audit_payload(structure_bars[-1]),
                    "latest_execution_bar": _bar_audit_payload(execution_bars[-1]),
                    # Preserve a short overlapping causal 1-minute window on
                    # every idempotent finalized-bar state event. Post-close
                    # replay can de-duplicate by bar start_time and detect
                    # missing minutes instead of reconstructing chart shape
                    # from daily OHLC or hindsight.
                    "causal_1m_bar_window": [
                        _bar_audit_payload(bar)
                        for bar in base_bars[-10:]
                    ],
                },
            )
            if config.config.stoch_trend_capture_enabled:
                try:
                    stoch_capture = evaluate_stoch_trend_capture(
                        base_bars,
                        entry_start_et=config.risk.entry_start_et,
                        last_entry_et=config.risk.last_entry_et,
                        force_flat_et=config.risk.force_flat_et,
                    )
                except Exception as exc:
                    trade_log(
                        "auto_trading",
                        "stoch_trend_capture_error",
                        run_id=self.current_run_id,
                        strategy_id=config.strategy_id,
                        universe_id=universe.universe_id,
                        instrument_id=candidate.instrument_id,
                        error_type=type(exc).__name__,
                        detail=str(exc),
                        research_only=True,
                        execution_authority=False,
                    )
                else:
                    stoch_observed_at = stoch_capture.as_of or base_bars[-1].end_time
                    await self._event(
                        strategy_repository,
                        config,
                        instrument_id=candidate.instrument_id,
                        event_type="stoch_trend_capture",
                        state=stoch_capture.state,
                        reason_code=stoch_capture.reason_code,
                        observed_at=stoch_observed_at,
                        payload={
                            "universe_id": universe.universe_id,
                            "universe_discovery_source": universe.discovery_source,
                            "morning_discovery_rank": candidate.discovery_rank,
                            "policy": stoch_capture.model_dump(mode="json"),
                            "research_only": True,
                            "execution_authority": False,
                        },
                    )

                    # Capture authoritative execution conditions exactly when the
                    # first 3m oversold signal becomes actionable. Later cycles
                    # must not backfill entry eligibility from changed quotes.
                    stoch_signal_key = (
                        candidate.instrument_id,
                        stoch_capture.entry_signal_time.astimezone(timezone.utc).isoformat(),
                    ) if stoch_capture.entry_signal_time is not None else None
                    if (
                        stoch_capture.state == "entry_armed"
                        and stoch_capture.entry_signal_time is not None
                        and stoch_execution_history_available
                        and stoch_signal_key not in captured_stoch_entry_signals
                    ):
                        try:
                            entry_evidence = await asyncio.to_thread(
                                observe_shadow_execution,
                                market_service,
                                instrument_id=candidate.instrument_id,
                                binding_id=candidate.binding_id,
                            )
                            risk_decision = stoch_trend_capture_risk_decision(
                                entry_evidence.execution,
                                max_spread_bps=config.risk.max_spread_bps,
                            )
                            entry_simulation = (
                                simulate_stoch_execution(
                                    entry_evidence.execution,
                                    action="entry",
                                    instrument_id=candidate.instrument_id,
                                    binding_id=candidate.binding_id,
                                    decision_at=stoch_capture.entry_signal_time,
                                    requested_fraction=Decimal("1"),
                                )
                                if risk_decision.allowed
                                else None
                            )
                            source_time = entry_evidence.execution.get("source_time")
                            capture_lag_seconds = None
                            if isinstance(source_time, datetime):
                                capture_lag_seconds = (
                                    source_time.astimezone(timezone.utc)
                                    - stoch_capture.entry_signal_time.astimezone(timezone.utc)
                                ).total_seconds()
                            entry_payload = {
                                "universe_id": universe.universe_id,
                                "policy_version": stoch_capture.policy_version,
                                "entry_signal_time": stoch_capture.entry_signal_time,
                                "execution_capture_observed_at": stoch_observed_at,
                                "execution_capture_lag_seconds": capture_lag_seconds,
                                "risk_decision": risk_decision.model_dump(mode="json"),
                                "execution": entry_evidence.execution,
                                "execution_simulation": (
                                    entry_simulation.model_dump(mode="json")
                                    if entry_simulation is not None
                                    else None
                                ),
                                "research_only": True,
                                "execution_authority": False,
                            }
                        except Exception as exc:
                            entry_payload = {
                                "universe_id": universe.universe_id,
                                "policy_version": stoch_capture.policy_version,
                                "entry_signal_time": stoch_capture.entry_signal_time,
                                "execution_capture_observed_at": stoch_observed_at,
                                "risk_decision": {
                                    "allowed": False,
                                    "reason_codes": ["STOCH_TREND_EXECUTION_EVIDENCE_ERROR"],
                                },
                                "execution_simulation": None,
                                "detail": f"{type(exc).__name__}: {exc}",
                                "research_only": True,
                                "execution_authority": False,
                            }
                        # Bind idempotency to the signal timestamp. If polling
                        # sees the same armed state more than once, the first
                        # causal capture wins rather than creating duplicates.
                        await self._event(
                            strategy_repository,
                            config,
                            instrument_id=candidate.instrument_id,
                            event_type="stoch_trend_capture_entry",
                            state="entry_evidence",
                            reason_code="STOCH_TREND_ENTRY_EVIDENCE_CAPTURED",
                            observed_at=stoch_capture.entry_signal_time,
                            payload=entry_payload,
                        )
                        assert stoch_signal_key is not None
                        captured_stoch_entry_signals.add(stoch_signal_key)
                        stoch_entry_payload_by_instrument[
                            candidate.instrument_id
                        ] = entry_payload
                    elif (
                        stoch_signal_key is not None
                        and stoch_capture.entry_time is not None
                        and stoch_execution_history_available
                        and stoch_signal_key not in captured_stoch_entry_signals
                    ):
                        # The monitor first observed this signal only after the
                        # next 3m bar was already finalized. Never backfill the
                        # entry with a later quote: persist an explicit
                        # fail-closed evidence record so reconstructed returns
                        # cannot masquerade as prospectively executable trades.
                        await self._event(
                            strategy_repository,
                            config,
                            instrument_id=candidate.instrument_id,
                            event_type="stoch_trend_capture_entry",
                            state="entry_evidence",
                            reason_code="STOCH_TREND_ENTRY_EVIDENCE_CAPTURED",
                            observed_at=stoch_capture.entry_signal_time,
                            payload={
                                "universe_id": universe.universe_id,
                                "policy_version": stoch_capture.policy_version,
                                "entry_signal_time": stoch_capture.entry_signal_time,
                                "entry_time": stoch_capture.entry_time,
                                "execution_capture_observed_at": stoch_observed_at,
                                "execution_capture_lag_seconds": None,
                                "risk_decision": {
                                    "allowed": False,
                                    "reason_codes": ["STOCH_TREND_ENTRY_EVIDENCE_MISSED"],
                                },
                                "execution": None,
                                "execution_simulation": None,
                                "detail": (
                                    "No point-in-time execution observation was captured "
                                    "before the next finalized 3m entry bar."
                                ),
                                "research_only": True,
                                "execution_authority": False,
                            },
                        )
                        captured_stoch_entry_signals.add(stoch_signal_key)
                        stoch_entry_payload_by_instrument[candidate.instrument_id] = {
                            "universe_id": universe.universe_id,
                            "policy_version": stoch_capture.policy_version,
                            "entry_signal_time": stoch_capture.entry_signal_time,
                            "entry_time": stoch_capture.entry_time,
                            "execution_capture_observed_at": stoch_observed_at,
                            "execution_capture_lag_seconds": None,
                            "risk_decision": {
                                "allowed": False,
                                "reason_codes": ["STOCH_TREND_ENTRY_EVIDENCE_MISSED"],
                            },
                            "execution": None,
                            "execution_simulation": None,
                            "detail": (
                                "No point-in-time execution observation was captured "
                                "before the next finalized 3m entry bar."
                            ),
                            "research_only": True,
                            "execution_authority": False,
                        }

            if config.config.stoch_trend_capture_enabled and stoch_capture is not None:
                execution_action = stoch_execution_action_for_snapshot(stoch_capture)
                if execution_action is not None and execution_action[0] != "entry":
                    action, action_time = execution_action
                    action_key = (
                        candidate.instrument_id,
                        action,
                        action_time.astimezone(timezone.utc).isoformat(),
                    )
                    if (
                        stoch_execution_history_available
                        and action_key not in captured_stoch_execution_actions
                    ):
                        try:
                            action_evidence = await asyncio.to_thread(
                                observe_shadow_execution,
                                market_service,
                                instrument_id=candidate.instrument_id,
                                binding_id=candidate.binding_id,
                            )
                            action_simulation = simulate_stoch_execution(
                                action_evidence.execution,
                                action=action,
                                instrument_id=candidate.instrument_id,
                                binding_id=candidate.binding_id,
                                decision_at=action_time,
                                requested_fraction=stoch_requested_fraction_for_action(
                                    action,
                                    stoch_capture,
                                ),
                                reference_price=(
                                    stoch_capture.runner_exit_price
                                    if action == "force_flat"
                                    else None
                                ),
                            )
                            action_payload = {
                                "universe_id": universe.universe_id,
                                "policy_version": stoch_capture.policy_version,
                                "action": action,
                                "decision_at": action_time,
                                "execution": action_evidence.execution,
                                "execution_simulation": action_simulation.model_dump(
                                    mode="json"
                                ),
                                "research_only": True,
                                "execution_authority": False,
                            }
                        except Exception as exc:
                            action_payload = {
                                "universe_id": universe.universe_id,
                                "policy_version": stoch_capture.policy_version,
                                "action": action,
                                "decision_at": action_time,
                                "execution": None,
                                "execution_simulation": None,
                                "detail": f"{type(exc).__name__}: {exc}",
                                "research_only": True,
                                "execution_authority": False,
                            }
                        await self._event(
                            strategy_repository,
                            config,
                            instrument_id=candidate.instrument_id,
                            event_type="stoch_trend_execution",
                            state=action,
                            reason_code="STOCH_EXECUTION_ACTION_CAPTURED",
                            observed_at=action_time,
                            payload=action_payload,
                        )
                        captured_stoch_execution_actions.add(action_key)
                        stoch_action_payloads_by_instrument.setdefault(
                            candidate.instrument_id,
                            {},
                        )[action] = action_payload

                missed_actions: list[tuple[StochExecutionAction, datetime]] = []
                if (
                    stoch_capture.state == "range_exited"
                    and stoch_capture.first_overbought_time is not None
                ):
                    missed_actions.append(
                        ("range_exit", stoch_capture.first_overbought_time)
                    )
                if (
                    stoch_capture.partial_exit_time is not None
                    and stoch_capture.first_overbought_time is not None
                ):
                    missed_actions.append(
                        ("partial_exit", stoch_capture.first_overbought_time)
                    )
                if (
                    stoch_capture.state == "trend_exited"
                    and stoch_capture.trend_break_time is not None
                ):
                    missed_actions.append(
                        ("runner_exit", stoch_capture.trend_break_time)
                    )

                for missed_action, missed_time in missed_actions:
                    missed_key = (
                        candidate.instrument_id,
                        missed_action,
                        missed_time.astimezone(timezone.utc).isoformat(),
                    )
                    if (
                        not stoch_execution_history_available
                        or missed_key in captured_stoch_execution_actions
                    ):
                        continue
                    missed_payload = {
                        "universe_id": universe.universe_id,
                        "policy_version": stoch_capture.policy_version,
                        "action": missed_action,
                        "decision_at": missed_time,
                        "execution": None,
                        "execution_simulation": None,
                        "detail": (
                            "No point-in-time bid/ask observation was captured "
                            "while this Stoch action was actionable."
                        ),
                        "research_only": True,
                        "execution_authority": False,
                    }
                    await self._event(
                        strategy_repository,
                        config,
                        instrument_id=candidate.instrument_id,
                        event_type="stoch_trend_execution",
                        state=missed_action,
                        reason_code="STOCH_EXECUTION_EVIDENCE_MISSED",
                        observed_at=missed_time,
                        payload=missed_payload,
                    )
                    captured_stoch_execution_actions.add(missed_key)
                    stoch_action_payloads_by_instrument.setdefault(
                        candidate.instrument_id,
                        {},
                    )[missed_action] = missed_payload

                if stoch_capture.state in {"range_exited", "trend_exited", "force_flat"}:
                    summary = build_stoch_execution_summary(
                        stoch_capture,
                        entry_payload=stoch_entry_payload_by_instrument.get(
                            candidate.instrument_id
                        ),
                        action_payloads=stoch_action_payloads_by_instrument.get(
                            candidate.instrument_id,
                            {},
                        ),
                    )
                    summary_at = (
                        stoch_capture.runner_exit_time
                        or stoch_capture.as_of
                        or stoch_observed_at
                    )
                    await self._event(
                        strategy_repository,
                        config,
                        instrument_id=candidate.instrument_id,
                        event_type="stoch_trend_execution_summary",
                        state="complete" if summary.complete else "incomplete",
                        reason_code=summary.reason_code,
                        observed_at=summary_at,
                        payload={
                            "universe_id": universe.universe_id,
                            "policy": summary.model_dump(mode="json"),
                            "research_only": True,
                            "execution_authority": False,
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
                    learning_rows.append((candidate, result, base_bars[-1].end_time, learning))
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
                    -row[3].execution_adjusted_opportunity_score,
                    -row[3].raw_movement_score,
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
                        "raw_movement_score": row[3].raw_movement_score,
                        "execution_adjusted_opportunity_score": row[3].execution_adjusted_opportunity_score,
                        "squeeze_probability_score": row[3].squeeze_probability_score,
                        "failed_selloff_probability_score": row[3].failed_selloff_probability_score,
                        "trend_continuation_score": row[3].trend_continuation_score,
                        "gap_retention_score": row[3].gap_retention_score,
                    }
                    for index, row in enumerate(ranked_learning, start=1)
                ],
                execution_authority=False,
            )

            await self._run_intraday_llm(
                config,
                strategy_repository,
                universe,
                ranked_learning,
            )

        proposals.sort(key=lambda proposal: proposal.priority)
        if evaluated_any or proposals:
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
        cycle_started_at = datetime.now(timezone.utc)
        log_cycle_heartbeat = self._should_log_diagnostic(
            ("strategy_cycle_heartbeat", config.strategy_id),
            cycle_started_at,
        )
        if log_cycle_heartbeat:
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
            if log_cycle_heartbeat:
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
                if log_cycle_heartbeat:
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
                resolve_v2_runtime_archive,
                config,
                strategy_repository,
                now=now_utc,
            )
            universe_source = (
                "auto_archive_auto_paper"
                if config.mode == "auto_paper"
                else "auto_archive_shadow"
            )
            if universe is None:
                if log_cycle_heartbeat:
                    reason = (
                        "v2_auto_paper_archive_not_ready"
                        if config.mode == "auto_paper"
                        and config.config.strategy_version == "2.0.0"
                        else (
                            "v2_shadow_archive_not_ready"
                            if config.mode == "shadow"
                            and config.config.strategy_version == "2.0.0"
                            else "no_active_universe"
                        )
                    )
                    trade_log(
                        "auto_trading",
                        "strategy_cycle_skipped",
                        run_id=self.current_run_id,
                        strategy_id=config.strategy_id,
                        reason=reason,
                        execution_authority=(config.mode == "auto_paper"),
                    )
                return

        integrity = assess_universe_integrity(universe)
        if log_cycle_heartbeat:
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
                capture_on_time=integrity.capture_on_time,
                cohort_complete=integrity.cohort_complete,
                cohort_integrity=integrity.cohort_integrity,
                market_data_complete=integrity.market_data_complete,
                prospective_eligible=integrity.prospective_eligible,
                integrity_reason_codes=integrity.reason_codes,
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

        if universe.discovery_source == "finviz" and not integrity.prospective_eligible:
            await self._event(
                strategy_repository,
                config,
                instrument_id="__universe__",
                event_type="universe_integrity",
                state="invalid",
                reason_code=(
                    integrity.reason_codes[0]
                    if integrity.reason_codes
                    else "UNIVERSE_DATA_INTEGRITY_INVALID"
                ),
                observed_at=universe.evaluation_time,
                payload={
                    "universe_id": universe.universe_id,
                    **integrity.model_dump(mode="json"),
                    "research_only": True,
                    "execution_authority": False,
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
        log_monitor_heartbeat = self._should_log_diagnostic(
            ("monitor_heartbeat",),
            started_at,
        )
        if log_monitor_heartbeat:
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
            if log_monitor_heartbeat or new_orders:
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
            "managed_finviz_shadow_provision": self.managed_finviz_shadow_provision,
            "managed_finviz_shadow_provision_error": self.managed_finviz_shadow_provision_error,
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
        if managed_finviz_shadow_autoprovision_enabled():
            try:
                provision = await asyncio.to_thread(
                    provision_managed_finviz_shadow_strategy,
                    strategy_repository=monitor.strategy_repository_factory(),
                    paper_repository=monitor.paper_repository_factory(),
                )
                monitor.managed_finviz_shadow_provision = provision.model_dump(mode="json")
                monitor.managed_finviz_shadow_provision_error = None
                if (
                    monitor.last_error is not None
                    and monitor.last_error.startswith(
                        "managed_finviz_shadow_provision:"
                    )
                ):
                    monitor.last_error = None
            except Exception as exc:
                monitor.managed_finviz_shadow_provision = None
                monitor.managed_finviz_shadow_provision_error = (
                    f"{type(exc).__name__}: {exc}"
                )
                monitor.last_error = (
                    "managed_finviz_shadow_provision: "
                    f"{type(exc).__name__}: {exc}"
                )
                trade_log(
                    "auto_trading",
                    "managed_finviz_shadow_provision_error",
                    error_type=type(exc).__name__,
                    detail=str(exc),
                )
        if trading_strategy_monitor_enabled():
            monitor.start()

    async def shutdown() -> None:
        await monitor.stop()

    gateway.router.add_event_handler("startup", startup)
    gateway.router.add_event_handler("shutdown", shutdown)
    return monitor
