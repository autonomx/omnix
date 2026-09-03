from __future__ import annotations

"""Four-arm Finviz Top-5 SHADOW experiment.

A/B (deterministic V2 and Stoch trend capture) are produced by the canonical
strategy monitor. This monitor adds C/D: a stateful every-minute AI policy and a
stateful event-driven AI policy over the identical frozen cohort. It never
creates paper orders or protections.
"""

import asyncio
import hashlib
import os
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI

from .indicator_signals import multi_timeframe_indicator_context
from .models import MarketBar
from .service import TradingMarketDataService, default_market_data_service
from .strategies import evaluate_gap_pullback
from .strategy_ai_shadow import (
    AI_SHADOW_POLICY_VERSION,
    AIShadowDecision,
    AIShadowPolicy,
    AIShadowPolicyAnalyzer,
    AIShadowPositionState,
    apply_fill,
    desired_fill,
    event_trigger_reasons,
    feature_snapshot,
    simulate_ai_shadow_fill,
)
from .strategy_intraday_learning import build_intraday_learning_snapshot
from .strategy_managed_finviz_shadow import MANAGED_FINVIZ_SHADOW_STRATEGY_ID
from .strategy_repository import (
    StrategyEvent,
    TradingStrategyConfigDocument,
    TradingStrategyRepository,
    default_strategy_repository,
)
from .strategy_shadow_execution import observe_shadow_execution
from .strategy_shadow_universe import resolve_v2_shadow_archive
from .strategy_timeframes import resample_final_bars
from .trade_logging import trade_log


_ET = ZoneInfo("America/New_York")
_STATE_KEY = "_omnix_trading_ai_shadow_monitor"
_EVENT_TYPES = (
    "state",
    "v2_shadow_replay_trade",
    "stoch_trend_execution_summary",
    "ai_shadow_decision",
    "ai_shadow_fill",
    "ai_shadow_trade",
    "ai_shadow_batch",
    "ai_shadow_session_summary",
    "shadow_strategy_comparison",
)
_EXECUTION_FIELDS = (
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


def _flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def ai_shadow_monitor_enabled() -> bool:
    if os.environ.get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return _flag("OMNIX_TRADING_AI_SHADOW_MONITOR_IN_TESTS", "0")
    return _flag("OMNIX_TRADING_AI_SHADOW_MONITOR", "1")


def _interval_seconds() -> float:
    try:
        value = float(os.environ.get("OMNIX_TRADING_AI_SHADOW_INTERVAL_SECONDS", "15"))
    except ValueError:
        value = 15.0
    return max(5.0, value)


def _key(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()


def _decimal(value: object) -> Decimal | None:
    if value in {None, ""}:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _eligible(config: TradingStrategyConfigDocument) -> bool:
    return (
        config.strategy_id == MANAGED_FINVIZ_SHADOW_STRATEGY_ID
        and config.enabled
        and config.mode == "shadow"
        and config.active_universe_id is None
        and config.config.strategy_version == "2.0.0"
        and config.config.universe_discovery_source == "finviz"
        and config.config.universe_discovery_count == 5
    )


def _execution_payload(observation: Any) -> dict[str, object]:
    payload = {field: getattr(observation, field, None) for field in _EXECUTION_FIELDS}
    spread = getattr(observation, "spread_bps", None)
    payload["spread_bps"] = spread
    return payload


def _position_from_latest_fill(
    events: list[StrategyEvent],
    *,
    policy: AIShadowPolicy,
    instrument_id: str,
) -> AIShadowPositionState:
    candidates = [
        event
        for event in events
        if event.event_type == "ai_shadow_fill"
        and event.instrument_id == instrument_id
        and event.payload.get("policy") == policy
        and isinstance(event.payload.get("position_after"), dict)
    ]
    if not candidates:
        return AIShadowPositionState(policy=policy, instrument_id=instrument_id)
    latest = max(candidates, key=lambda event: (event.observed_at, event.event_id))
    try:
        return AIShadowPositionState.model_validate(latest.payload["position_after"])
    except Exception:
        return AIShadowPositionState(policy=policy, instrument_id=instrument_id)


def _previous_decision(
    events: list[StrategyEvent],
    *,
    policy: AIShadowPolicy,
    instrument_id: str,
) -> StrategyEvent | None:
    matches = [
        event
        for event in events
        if event.event_type == "ai_shadow_decision"
        and event.instrument_id == instrument_id
        and event.payload.get("policy") == policy
    ]
    return max(matches, key=lambda event: (event.observed_at, event.event_id)) if matches else None


def _decision_exists(
    events: list[StrategyEvent],
    *,
    policy: AIShadowPolicy,
    instrument_id: str,
    observed_at: datetime,
) -> bool:
    target = observed_at.astimezone(timezone.utc)
    return any(
        event.event_type == "ai_shadow_decision"
        and event.instrument_id == instrument_id
        and event.payload.get("policy") == policy
        and event.observed_at.astimezone(timezone.utc) == target
        for event in events
    )


def _action_changes(
    events: list[StrategyEvent],
    *,
    policy: AIShadowPolicy,
    instrument_id: str,
    start: datetime,
    end: datetime,
) -> tuple[int, int, int]:
    decisions = sorted(
        [
            event
            for event in events
            if event.event_type == "ai_shadow_decision"
            and event.instrument_id == instrument_id
            and event.payload.get("policy") == policy
            and start <= event.observed_at <= end
        ],
        key=lambda event: event.observed_at,
    )
    actions = [str(event.payload.get("effective_action") or event.payload.get("decision", {}).get("action") or "") for event in decisions]
    changes = sum(1 for left, right in zip(actions, actions[1:]) if left and right and left != right)
    allocated_tokens = sum(int(event.payload.get("allocated_tokens") or 0) for event in decisions)
    return len(decisions), changes, allocated_tokens


def _max_drawdown(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    equity = Decimal("0")
    peak = Decimal("0")
    worst = Decimal("0")
    for value in values:
        equity += value
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def _mfe_mae(
    bars: list[MarketBar],
    *,
    entry_time: datetime,
    exit_time: datetime,
    entry_price: Decimal,
) -> tuple[Decimal | None, Decimal | None]:
    window = [
        bar
        for bar in bars
        if bar.is_final
        and bar.session == "regular"
        and bar.end_time >= entry_time
        and bar.start_time <= exit_time
    ]
    if not window or entry_price <= 0:
        return None, None
    mfe = max((bar.high / entry_price - Decimal("1")) * Decimal("100") for bar in window)
    mae = min((bar.low / entry_price - Decimal("1")) * Decimal("100") for bar in window)
    return mfe, mae


class TradingAIShadowMonitor:
    def __init__(
        self,
        *,
        strategy_repository_factory: Callable[[], TradingStrategyRepository] = default_strategy_repository,
        market_service_factory: Callable[[], TradingMarketDataService] = default_market_data_service,
        analyzer_factory: Callable[[], AIShadowPolicyAnalyzer] = AIShadowPolicyAnalyzer,
        now_factory: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        interval_seconds: float | None = None,
    ) -> None:
        self.strategy_repository_factory = strategy_repository_factory
        self.market_service_factory = market_service_factory
        self.analyzer_factory = analyzer_factory
        self.now_factory = now_factory
        self.interval_seconds = interval_seconds or _interval_seconds()
        self._task: asyncio.Task[None] | None = None
        self.last_run_at: datetime | None = None
        self.last_error: str | None = None
        self.minute_llm_call_count = 0
        self.event_llm_call_count = 0
        self.decision_count = 0
        self.fill_count = 0
        self.trade_count = 0
        self.total_token_count = 0

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

    async def _append(
        self,
        repository: TradingStrategyRepository,
        config: TradingStrategyConfigDocument,
        *,
        instrument_id: str,
        event_type: str,
        state: str,
        reason_code: str,
        observed_at: datetime,
        payload: dict[str, object],
        identity: tuple[object, ...],
    ) -> bool:
        idem = _key(
            config.strategy_id,
            AI_SHADOW_POLICY_VERSION,
            instrument_id,
            event_type,
            *identity,
        )
        return await asyncio.to_thread(
            repository.append_event,
            StrategyEvent(
                strategy_id=config.strategy_id,
                event_id=idem[:32],
                run_id=f"ai-shadow-{observed_at.astimezone(timezone.utc).strftime('%Y%m%d')}",
                instrument_id=instrument_id,
                event_type=event_type,
                state=state,
                reason_code=reason_code,
                observed_at=observed_at,
                idempotency_key=idem,
                payload=payload,
            ),
        )

    async def _session_events(
        self,
        repository: TradingStrategyRepository,
        config: TradingStrategyConfigDocument,
        *,
        session_date,
        now: datetime,
    ) -> list[StrategyEvent]:
        start_et = datetime(
            session_date.year,
            session_date.month,
            session_date.day,
            tzinfo=_ET,
        )
        end = min(now + timedelta(seconds=1), start_et + timedelta(days=1))
        if hasattr(repository, "events_by_types_between"):
            return await asyncio.to_thread(
                repository.events_by_types_between,
                config.strategy_id,
                event_types=_EVENT_TYPES,
                start_time=start_et.astimezone(timezone.utc),
                end_time=end.astimezone(timezone.utc),
                limit=20_000,
            )
        recent = await asyncio.to_thread(repository.recent_events, config.strategy_id, 20_000)
        return [
            event
            for event in recent
            if event.event_type in _EVENT_TYPES
            and start_et.astimezone(timezone.utc)
            <= event.observed_at.astimezone(timezone.utc)
            < end.astimezone(timezone.utc)
        ]

    async def _apply_decision(
        self,
        *,
        policy: AIShadowPolicy,
        decision: AIShadowDecision,
        row: dict[str, object],
        candidate,
        bars: list[MarketBar],
        config: TradingStrategyConfigDocument,
        repository: TradingStrategyRepository,
        market_service: TradingMarketDataService,
        events: list[StrategyEvent],
        result,
        batch_result,
        trigger_reasons: tuple[str, ...],
    ) -> None:
        observed_at = row["observed_at"]
        assert isinstance(observed_at, datetime)
        position = _position_from_latest_fill(
            events,
            policy=policy,
            instrument_id=candidate.instrument_id,
        )
        effective_action = decision.action
        observed_et = observed_at.astimezone(_ET).time()
        force_flat = position.is_long and observed_et >= config.risk.force_flat_et
        if force_flat:
            effective_action = "exit"

        previous = _previous_decision(
            events,
            policy=policy,
            instrument_id=candidate.instrument_id,
        )
        previous_action = None
        if previous is not None:
            previous_action = previous.payload.get("effective_action")
            if previous_action is None and isinstance(previous.payload.get("decision"), dict):
                previous_action = previous.payload["decision"].get("action")

        allocation = (
            batch_result.total_tokens // max(1, len(batch_result.decisions))
            if batch_result is not None
            else 0
        )
        decision_payload: dict[str, object] = {
            "policy_version": AI_SHADOW_POLICY_VERSION,
            "policy": policy,
            "universe_id": row["universe_id"],
            "decision": decision.model_dump(mode="json"),
            "effective_action": effective_action,
            "force_flat_override": force_flat,
            "trigger_reasons": list(trigger_reasons),
            "feature_snapshot": row["feature_snapshot"],
            "previous_action": previous_action,
            "position_before": position.model_dump(mode="json"),
            "provider": batch_result.provider if batch_result is not None else "system",
            "model": batch_result.model if batch_result is not None else None,
            "allocated_tokens": allocation,
            "research_only": True,
            "execution_authority": False,
        }
        persisted = await self._append(
            repository,
            config,
            instrument_id=candidate.instrument_id,
            event_type="ai_shadow_decision",
            state=effective_action,
            reason_code=(
                "AI_SHADOW_FORCE_FLAT"
                if force_flat
                else "AI_SHADOW_MINUTE_DECISION"
                if policy == "minute"
                else "AI_SHADOW_EVENT_DECISION"
            ),
            observed_at=observed_at,
            payload=decision_payload,
            identity=(policy, observed_at.astimezone(timezone.utc).isoformat()),
        )
        if persisted:
            self.decision_count += 1
            events.append(
                StrategyEvent(
                    strategy_id=config.strategy_id,
                    event_id=_key(policy, candidate.instrument_id, observed_at)[:32],
                    run_id="ai-shadow-local",
                    instrument_id=candidate.instrument_id,
                    event_type="ai_shadow_decision",
                    state=effective_action,
                    reason_code="AI_SHADOW_DECISION",
                    observed_at=observed_at,
                    idempotency_key=_key(policy, candidate.instrument_id, observed_at),
                    payload=decision_payload,
                )
            )

        effective_decision = decision.model_copy(update={"action": effective_action})
        side, units = desired_fill(effective_decision, position)
        if side is None or units <= 0:
            return

        try:
            evidence = await asyncio.to_thread(
                observe_shadow_execution,
                market_service,
                instrument_id=candidate.instrument_id,
                binding_id=candidate.binding_id,
            )
            execution = evidence.execution
        except Exception as exc:
            await self._append(
                repository,
                config,
                instrument_id=candidate.instrument_id,
                event_type="ai_shadow_fill",
                state="unfilled",
                reason_code="AI_SHADOW_EXECUTION_EVIDENCE_ERROR",
                observed_at=observed_at,
                payload={
                    "policy": policy,
                    "decision_at": observed_at,
                    "side": side,
                    "requested_units": str(units),
                    "detail": f"{type(exc).__name__}: {exc}",
                    "position_before": position.model_dump(mode="json"),
                    "position_after": position.model_dump(mode="json"),
                    "research_only": True,
                    "execution_authority": False,
                },
                identity=(policy, observed_at.astimezone(timezone.utc).isoformat(), "fill"),
            )
            return

        if side == "buy":
            spread = execution.get("spread_bps")
            spread_value = Decimal(str(spread)) if spread is not None else None
            allowed = (
                execution.get("execution_eligible") is True
                and execution.get("halted") is not True
                and spread_value is not None
                and spread_value <= config.risk.max_spread_bps
            )
            if not allowed:
                await self._append(
                    repository,
                    config,
                    instrument_id=candidate.instrument_id,
                    event_type="ai_shadow_fill",
                    state="vetoed",
                    reason_code="AI_SHADOW_ENTRY_EXECUTION_VETO",
                    observed_at=observed_at,
                    payload={
                        "policy": policy,
                        "decision_at": observed_at,
                        "side": side,
                        "requested_units": str(units),
                        "execution": execution,
                        "position_before": position.model_dump(mode="json"),
                        "position_after": position.model_dump(mode="json"),
                        "research_only": True,
                        "execution_authority": False,
                    },
                    identity=(policy, observed_at.astimezone(timezone.utc).isoformat(), "fill"),
                )
                return

        simulation = simulate_ai_shadow_fill(
            execution,
            side=side,
            instrument_id=candidate.instrument_id,
            binding_id=candidate.binding_id,
            decision_at=observed_at,
            requested_units=units,
            reference_price=result.current_price,
        )
        trade_id = position.trade_id or _key(
            policy,
            candidate.instrument_id,
            observed_at.astimezone(timezone.utc).isoformat(),
            "trade",
        )[:24]
        after = apply_fill(position, simulation, trade_id=trade_id)
        fill_time = simulation.source_time or observed_at
        closed_trade = position.is_long and not after.is_long and simulation.should_fill
        persisted_after = (
            AIShadowPositionState(policy=policy, instrument_id=candidate.instrument_id)
            if closed_trade
            else after
        )
        fill_payload = {
            "policy_version": AI_SHADOW_POLICY_VERSION,
            "policy": policy,
            "trade_id": trade_id,
            "decision_at": observed_at,
            "side": side,
            "requested_units": str(units),
            "simulation": simulation.model_dump(mode="json"),
            "position_before": position.model_dump(mode="json"),
            "position_after": persisted_after.model_dump(mode="json"),
            "closed_position": after.model_dump(mode="json") if closed_trade else None,
            "research_only": True,
            "execution_authority": False,
        }
        fill_persisted = await self._append(
            repository,
            config,
            instrument_id=candidate.instrument_id,
            event_type="ai_shadow_fill",
            state="filled" if simulation.should_fill else "unfilled",
            reason_code=(
                "AI_SHADOW_FILL_SIMULATED"
                if simulation.should_fill
                else "AI_SHADOW_FILL_NOT_EXECUTABLE"
            ),
            observed_at=fill_time,
            payload=fill_payload,
            identity=(policy, observed_at.astimezone(timezone.utc).isoformat(), "fill"),
        )
        if fill_persisted and simulation.should_fill:
            self.fill_count += 1
            events.append(
                StrategyEvent(
                    strategy_id=config.strategy_id,
                    event_id=_key(policy, candidate.instrument_id, observed_at, "fill")[:32],
                    run_id="ai-shadow-local",
                    instrument_id=candidate.instrument_id,
                    event_type="ai_shadow_fill",
                    state="filled",
                    reason_code="AI_SHADOW_FILL_SIMULATED",
                    observed_at=fill_time,
                    idempotency_key=_key(policy, candidate.instrument_id, observed_at, "fill"),
                    payload=fill_payload,
                )
            )

        if closed_trade:
            assert after.entry_time is not None
            assert after.first_entry_price is not None
            net_return = (
                after.realized_pnl / after.total_buy_notional * Decimal("100")
                if after.total_buy_notional > 0
                else None
            )
            reference_return = (
                (after.realized_pnl + after.execution_drag_dollars)
                / after.total_reference_buy_notional
                * Decimal("100")
                if after.total_reference_buy_notional > 0
                else None
            )
            drag_pct = (
                after.execution_drag_dollars
                / after.total_reference_buy_notional
                * Decimal("100")
                if after.total_reference_buy_notional > 0
                else None
            )
            mfe, mae = _mfe_mae(
                bars,
                entry_time=after.entry_time,
                exit_time=fill_time,
                entry_price=after.first_entry_price,
            )
            decision_count, action_changes, tokens = _action_changes(
                events,
                policy=policy,
                instrument_id=candidate.instrument_id,
                start=after.entry_time,
                end=fill_time,
            )
            trade_payload = {
                "policy_version": AI_SHADOW_POLICY_VERSION,
                "policy": policy,
                "trade_id": trade_id,
                "entry_time": after.entry_time,
                "exit_time": fill_time,
                "hold_minutes": str(
                    Decimal(str((fill_time - after.entry_time).total_seconds())) / Decimal("60")
                ),
                "first_entry_price": str(after.first_entry_price),
                "total_buy_notional": str(after.total_buy_notional),
                "realized_pnl_per_normalized_position": str(after.realized_pnl),
                "reference_return_pct": str(reference_return) if reference_return is not None else None,
                "net_execution_return_pct": str(net_return) if net_return is not None else None,
                "execution_drag_pct": str(drag_pct) if drag_pct is not None else None,
                "mfe_pct": str(mfe) if mfe is not None else None,
                "mae_pct": str(mae) if mae is not None else None,
                "fill_count": after.fill_count,
                "decision_count": decision_count,
                "action_change_count": action_changes,
                "decision_stability": (
                    str(Decimal("1") - Decimal(action_changes) / Decimal(max(1, decision_count - 1)))
                    if decision_count > 1
                    else "1"
                ),
                "allocated_llm_tokens": tokens,
                "research_only": True,
                "execution_authority": False,
            }
            trade_persisted = await self._append(
                repository,
                config,
                instrument_id=candidate.instrument_id,
                event_type="ai_shadow_trade",
                state="closed",
                reason_code="AI_SHADOW_TRADE_CLOSED",
                observed_at=fill_time,
                payload=trade_payload,
                identity=(policy, trade_id, "closed"),
            )
            if trade_persisted:
                self.trade_count += 1

    async def _run_policy(
        self,
        *,
        policy: AIShadowPolicy,
        rows: list[dict[str, object]],
        config: TradingStrategyConfigDocument,
        repository: TradingStrategyRepository,
        market_service: TradingMarketDataService,
        events: list[StrategyEvent],
    ) -> None:
        due: list[dict[str, object]] = []
        reasons_by_id: dict[str, tuple[str, ...]] = {}
        for row in rows:
            candidate = row["candidate"]
            observed_at = row["observed_at"]
            assert isinstance(observed_at, datetime)
            if observed_at.astimezone(_ET).time() >= config.risk.force_flat_et:
                continue
            if _decision_exists(
                events,
                policy=policy,
                instrument_id=candidate.instrument_id,
                observed_at=observed_at,
            ):
                continue
            previous = _previous_decision(
                events,
                policy=policy,
                instrument_id=candidate.instrument_id,
            )
            previous_feature = (
                previous.payload.get("feature_snapshot")
                if previous is not None
                and isinstance(previous.payload.get("feature_snapshot"), dict)
                else None
            )
            previous_decision = (
                previous.payload.get("decision")
                if previous is not None
                and isinstance(previous.payload.get("decision"), dict)
                else None
            )
            if policy == "event":
                reasons = event_trigger_reasons(
                    row["feature_snapshot"],
                    previous_feature,
                    prior_decision=previous_decision,
                )
                if not reasons:
                    continue
            else:
                reasons = ("completed_1m_bar",)

            analyzer_row = {
                "instrument_id": candidate.instrument_id,
                "observed_at": observed_at.isoformat(),
                "trigger_reasons": list(reasons),
                "feature_snapshot": row["feature_snapshot"],
                "previous_decision": previous_decision,
            }
            due.append({**row, "analyzer_row": analyzer_row})
            reasons_by_id[candidate.instrument_id] = reasons

        if not due:
            return

        analyzer = self.analyzer_factory()
        if policy == "minute":
            self.minute_llm_call_count += 1
        else:
            self.event_llm_call_count += 1
        try:
            batch = await asyncio.to_thread(
                analyzer.assess,
                policy=policy,
                rows=[row["analyzer_row"] for row in due],
            )
        except Exception as exc:
            observed_at = max(row["observed_at"] for row in due)
            assert isinstance(observed_at, datetime)
            await self._append(
                repository,
                config,
                instrument_id="__universe__",
                event_type="ai_shadow_batch",
                state="error",
                reason_code="AI_SHADOW_LLM_BATCH_ERROR",
                observed_at=observed_at,
                payload={
                    "policy": policy,
                    "error_type": type(exc).__name__,
                    "detail": str(exc),
                    "requested_instrument_ids": [
                        row["candidate"].instrument_id for row in due
                    ],
                    "research_only": True,
                    "execution_authority": False,
                },
                identity=(policy, observed_at.astimezone(timezone.utc).isoformat(), "error"),
            )
            trade_log(
                "auto_trading",
                "ai_shadow_llm_error",
                strategy_id=config.strategy_id,
                policy=policy,
                error_type=type(exc).__name__,
                detail=str(exc),
                execution_authority=False,
            )
            return

        self.total_token_count += batch.total_tokens
        observed_at = max(row["observed_at"] for row in due)
        assert isinstance(observed_at, datetime)
        await self._append(
            repository,
            config,
            instrument_id="__universe__",
            event_type="ai_shadow_batch",
            state="complete",
            reason_code="AI_SHADOW_LLM_BATCH_COMPLETE",
            observed_at=observed_at,
            payload={
                "policy": policy,
                "provider": batch.provider,
                "model": batch.model,
                "decision_count": len(batch.decisions),
                "input_tokens": batch.input_tokens,
                "output_tokens": batch.output_tokens,
                "total_tokens": batch.total_tokens,
                "usage_source": batch.usage_source,
                "research_only": True,
                "execution_authority": False,
            },
            identity=(policy, observed_at.astimezone(timezone.utc).isoformat(), "batch"),
        )

        by_id = {row["candidate"].instrument_id: row for row in due}
        for decision in batch.decisions:
            row = by_id.get(decision.instrument_id)
            if row is None:
                continue
            await self._apply_decision(
                policy=policy,
                decision=decision,
                row=row,
                candidate=row["candidate"],
                bars=row["bars"],
                config=config,
                repository=repository,
                market_service=market_service,
                events=events,
                result=row["learning"],
                batch_result=batch,
                trigger_reasons=reasons_by_id.get(decision.instrument_id, ()),
            )

    async def _force_flat_open_positions(
        self,
        *,
        rows: list[dict[str, object]],
        config: TradingStrategyConfigDocument,
        repository: TradingStrategyRepository,
        market_service: TradingMarketDataService,
        events: list[StrategyEvent],
        now: datetime,
    ) -> None:
        now_et = now.astimezone(_ET)
        if now_et.time() < config.risk.force_flat_et or now_et.time() >= time(16, 0):
            return
        for policy in ("minute", "event"):
            for row in rows:
                candidate = row["candidate"]
                position = _position_from_latest_fill(
                    events,
                    policy=policy,
                    instrument_id=candidate.instrument_id,
                )
                if not position.is_long:
                    continue
                synthetic = AIShadowDecision(
                    instrument_id=candidate.instrument_id,
                    action="exit",
                    confidence=100,
                    market_regime="unresolved",
                    expected_horizon_minutes=1,
                    thesis="Force-flat safety boundary.",
                    reason="The configured regular-session force-flat time has been reached.",
                    invalidation_price=None,
                )
                forced_row = dict(row)
                forced_row["observed_at"] = now
                await self._apply_decision(
                    policy=policy,
                    decision=synthetic,
                    row=forced_row,
                    candidate=candidate,
                    bars=row["bars"],
                    config=config,
                    repository=repository,
                    market_service=market_service,
                    events=events,
                    result=row["learning"],
                    batch_result=None,
                    trigger_reasons=("force_flat",),
                )

    async def _mark_incomplete_open_trades(
        self,
        *,
        config: TradingStrategyConfigDocument,
        repository: TradingStrategyRepository,
        events: list[StrategyEvent],
        session_date,
        now: datetime,
    ) -> None:
        if now.astimezone(_ET).time() < time(16, 0):
            return
        for policy in ("minute", "event"):
            instrument_ids = {
                event.instrument_id
                for event in events
                if event.event_type == "ai_shadow_fill"
                and event.payload.get("policy") == policy
                and event.instrument_id != "__universe__"
            }
            for instrument_id in sorted(instrument_ids):
                position = _position_from_latest_fill(
                    events,
                    policy=policy,
                    instrument_id=instrument_id,
                )
                if not position.is_long or not position.trade_id:
                    continue
                already_recorded = any(
                    event.event_type == "ai_shadow_trade"
                    and event.payload.get("policy") == policy
                    and event.payload.get("trade_id") == position.trade_id
                    for event in events
                )
                if already_recorded:
                    continue
                await self._append(
                    repository,
                    config,
                    instrument_id=instrument_id,
                    event_type="ai_shadow_trade",
                    state="incomplete",
                    reason_code="AI_SHADOW_FORCE_FLAT_EXECUTION_INCOMPLETE",
                    observed_at=now,
                    payload={
                        "policy_version": AI_SHADOW_POLICY_VERSION,
                        "policy": policy,
                        "trade_id": position.trade_id,
                        "session_date": session_date.isoformat(),
                        "entry_time": position.entry_time,
                        "position": position.model_dump(mode="json"),
                        "data_complete": False,
                        "net_execution_return_pct": None,
                        "detail": (
                            "The normalized SHADOW position remained open after "
                            "the force-flat boundary because no executable exit "
                            "fill was captured. No return is synthesized."
                        ),
                        "research_only": True,
                        "execution_authority": False,
                    },
                    identity=(policy, position.trade_id, "incomplete"),
                )

    async def _session_summary(
        self,
        *,
        config: TradingStrategyConfigDocument,
        repository: TradingStrategyRepository,
        events: list[StrategyEvent],
        session_date,
        now: datetime,
    ) -> None:
        if now.astimezone(_ET).time() < time(16, 0):
            return
        for policy in ("minute", "event"):
            all_trades = sorted(
                [
                    event
                    for event in events
                    if event.event_type == "ai_shadow_trade"
                    and event.payload.get("policy") == policy
                ],
                key=lambda event: event.observed_at,
            )
            trades = [event for event in all_trades if event.state == "closed"]
            incomplete_trades = [
                event for event in all_trades if event.state == "incomplete"
            ]
            returns = [
                Decimal(str(event.payload["net_execution_return_pct"]))
                for event in trades
                if event.payload.get("net_execution_return_pct") is not None
            ]
            drags = [
                Decimal(str(event.payload["execution_drag_pct"]))
                for event in trades
                if event.payload.get("execution_drag_pct") is not None
            ]
            stabilities = [
                Decimal(str(event.payload["decision_stability"]))
                for event in trades
                if event.payload.get("decision_stability") is not None
            ]
            payload = {
                "policy_version": AI_SHADOW_POLICY_VERSION,
                "policy": policy,
                "session_date": session_date.isoformat(),
                "trade_count": len(trades),
                "incomplete_trade_count": len(incomplete_trades),
                "win_count": sum(1 for value in returns if value > 0),
                "loss_count": sum(1 for value in returns if value < 0),
                "mean_net_return_pct": (
                    str(sum(returns, Decimal("0")) / Decimal(len(returns)))
                    if returns
                    else None
                ),
                "trade_sequence_max_drawdown_pct": (
                    str(_max_drawdown(returns)) if returns else None
                ),
                "mean_execution_drag_pct": (
                    str(sum(drags, Decimal("0")) / Decimal(len(drags)))
                    if drags
                    else None
                ),
                "total_decisions": sum(
                    int(event.payload.get("decision_count") or 0) for event in trades
                ),
                "total_action_changes": sum(
                    int(event.payload.get("action_change_count") or 0) for event in trades
                ),
                "median_not_reported": True,
                "mean_decision_stability": (
                    str(sum(stabilities, Decimal("0")) / Decimal(len(stabilities)))
                    if stabilities
                    else None
                ),
                "allocated_llm_tokens": sum(
                    int(event.payload.get("allocated_llm_tokens") or 0)
                    for event in trades
                ),
                "research_only": True,
                "execution_authority": False,
            }
            await self._append(
                repository,
                config,
                instrument_id="__universe__",
                event_type="ai_shadow_session_summary",
                state="complete",
                reason_code="AI_SHADOW_SESSION_SUMMARY",
                observed_at=now,
                payload=payload,
                identity=(
                    policy,
                    session_date.isoformat(),
                    _key(
                        len(all_trades),
                        [event.event_id for event in all_trades],
                        payload.get("allocated_llm_tokens"),
                    ),
                    "summary",
                ),
            )

    async def _comparison_summary(
        self,
        *,
        config: TradingStrategyConfigDocument,
        repository: TradingStrategyRepository,
        events: list[StrategyEvent],
        session_date,
        now: datetime,
    ) -> None:
        if now.astimezone(_ET).time() < time(16, 0):
            return

        deterministic_replays = sorted(
            [
                event for event in events if event.event_type == "v2_shadow_replay_trade"
            ],
            key=lambda event: str(event.payload.get("entry_time") or event.observed_at.isoformat()),
        )
        deterministic_r = [
            value
            for event in deterministic_replays
            if (value := _decimal(event.payload.get("r_result"))) is not None
        ]
        deterministic_r_drawdown = _max_drawdown(deterministic_r)
        entry_ready_events = [
            event
            for event in events
            if event.event_type == "state" and event.state == "entry_ready"
        ]

        stoch_events = sorted(
            [
                event for event in events if event.event_type == "stoch_trend_execution_summary"
            ],
            key=lambda event: event.observed_at,
        )
        stoch_net: list[Decimal] = []
        stoch_drag: list[Decimal] = []
        for event in stoch_events:
            policy_payload = event.payload.get("policy")
            if not isinstance(policy_payload, dict) or policy_payload.get("complete") is not True:
                continue
            value = _decimal(policy_payload.get("net_execution_return_pct"))
            if value is not None:
                stoch_net.append(value)
            drag = _decimal(policy_payload.get("execution_drag_pct"))
            if drag is not None:
                stoch_drag.append(drag)

        def ai_arm(policy: AIShadowPolicy) -> dict[str, object]:
            all_trades = sorted(
                [
                    event
                    for event in events
                    if event.event_type == "ai_shadow_trade"
                    and event.payload.get("policy") == policy
                ],
                key=lambda event: event.observed_at,
            )
            trades = [event for event in all_trades if event.state == "closed"]
            incomplete_trades = [
                event for event in all_trades if event.state == "incomplete"
            ]
            returns = [
                value
                for event in trades
                if (value := _decimal(event.payload.get("net_execution_return_pct"))) is not None
            ]
            maes = [
                value
                for event in trades
                if (value := _decimal(event.payload.get("mae_pct"))) is not None
            ]
            stabilities = [
                value
                for event in trades
                if (value := _decimal(event.payload.get("decision_stability"))) is not None
            ]
            drags = [
                value
                for event in trades
                if (value := _decimal(event.payload.get("execution_drag_pct"))) is not None
            ]
            batches = [
                event
                for event in events
                if event.event_type == "ai_shadow_batch"
                and event.payload.get("policy") == policy
                and event.state == "complete"
            ]
            return {
                "trade_count": len(trades),
                "incomplete_trade_count": len(incomplete_trades),
                "win_count": sum(1 for value in returns if value > 0),
                "mean_net_execution_return_pct": (
                    str(sum(returns, Decimal("0")) / Decimal(len(returns)))
                    if returns
                    else None
                ),
                "trade_sequence_max_drawdown_pct": (
                    str(_max_drawdown(returns)) if returns else None
                ),
                "worst_mae_pct": str(min(maes)) if maes else None,
                "mean_execution_drag_pct": (
                    str(sum(drags, Decimal("0")) / Decimal(len(drags)))
                    if drags
                    else None
                ),
                "total_decisions": sum(
                    int(event.payload.get("decision_count") or 0) for event in trades
                ),
                "total_action_changes": sum(
                    int(event.payload.get("action_change_count") or 0) for event in trades
                ),
                "mean_decision_stability": (
                    str(sum(stabilities, Decimal("0")) / Decimal(len(stabilities)))
                    if stabilities
                    else None
                ),
                "llm_call_count": len(batches),
                "llm_total_tokens": sum(
                    int(event.payload.get("total_tokens") or 0) for event in batches
                ),
            }

        payload = {
            "policy_version": AI_SHADOW_POLICY_VERSION,
            "session_date": session_date.isoformat(),
            "comparison_basis": "same frozen Finviz Top-5 cohort; causal SHADOW evidence",
            "arm_a_deterministic_v2": {
                "entry_ready_event_count": len(entry_ready_events),
                "replay_trade_count": len(deterministic_replays),
                "mean_r_result": (
                    str(sum(deterministic_r, Decimal("0")) / Decimal(len(deterministic_r)))
                    if deterministic_r
                    else None
                ),
                "trade_sequence_max_drawdown_r": (
                    str(deterministic_r_drawdown)
                    if deterministic_r_drawdown is not None
                    else None
                ),
                "return_unit": "R",
            },
            "arm_b_stoch_trend": {
                "completed_trade_count": len(stoch_net),
                "mean_net_execution_return_pct": (
                    str(sum(stoch_net, Decimal("0")) / Decimal(len(stoch_net)))
                    if stoch_net
                    else None
                ),
                "trade_sequence_max_drawdown_pct": (
                    str(_max_drawdown(stoch_net)) if stoch_net else None
                ),
                "mean_execution_drag_pct": (
                    str(sum(stoch_drag, Decimal("0")) / Decimal(len(stoch_drag)))
                    if stoch_drag
                    else None
                ),
                "return_unit": "percent",
            },
            "arm_c_ai_every_minute": ai_arm("minute"),
            "arm_d_ai_event_driven": ai_arm("event"),
            "cross_arm_return_units_harmonized": False,
            "ranking_deferred_until_risk_normalized": True,
            "research_only": True,
            "execution_authority": False,
        }
        identity_signature = _key(
            len(deterministic_replays),
            len(stoch_net),
            payload["arm_c_ai_every_minute"],
            payload["arm_d_ai_event_driven"],
        )
        await self._append(
            repository,
            config,
            instrument_id="__universe__",
            event_type="shadow_strategy_comparison",
            state="snapshot",
            reason_code="SHADOW_STRATEGY_COMPARISON_SNAPSHOT",
            observed_at=now,
            payload=payload,
            identity=(session_date.isoformat(), identity_signature),
        )

    async def _run_config(
        self,
        config: TradingStrategyConfigDocument,
        repository: TradingStrategyRepository,
        market_service: TradingMarketDataService,
        *,
        now: datetime,
    ) -> None:
        universe = await asyncio.to_thread(
            resolve_v2_shadow_archive,
            config,
            repository,
            now=now,
        )
        if universe is None:
            return
        events = await self._session_events(
            repository,
            config,
            session_date=universe.session_date,
            now=now,
        )

        rows: list[dict[str, object]] = []
        for rank, candidate in enumerate(universe.candidates, start=1):
            try:
                response = await asyncio.to_thread(
                    market_service.bars,
                    candidate.instrument_id,
                    "1m",
                    500,
                    candidate.binding_id,
                )
                bars = sorted(
                    [bar for bar in response.bars if bar.is_final and bar.end_time <= now],
                    key=lambda bar: bar.end_time,
                )
                structure = list(resample_final_bars(bars, config.config.structure_interval))
                if not structure:
                    continue
                result = evaluate_gap_pullback(candidate, structure, config.config)
                observed_at = structure[-1].end_time
                observed_et = observed_at.astimezone(_ET).time()
                if observed_et < config.config.entry_start_et:
                    continue
                learning = build_intraday_learning_snapshot(candidate, result, bars)
                indicators = multi_timeframe_indicator_context(bars)
                try:
                    execution_observation = await asyncio.to_thread(
                        market_service.execution_observation,
                        candidate.instrument_id,
                        candidate.binding_id,
                    )
                    execution = _execution_payload(execution_observation)
                except Exception:
                    execution = {
                        "bid": None,
                        "ask": None,
                        "last": str(learning.current_price),
                        "spread_bps": None,
                        "execution_eligible": False,
                        "halted": None,
                        "freshness_mode": "unknown",
                        "rejection_reasons": ("EXECUTION_OBSERVATION_UNAVAILABLE",),
                    }
                positions = {
                    policy: _position_from_latest_fill(
                        events,
                        policy=policy,
                        instrument_id=candidate.instrument_id,
                    )
                    for policy in ("minute", "event")
                }
                rows.append(
                    {
                        "candidate": candidate,
                        "bars": bars,
                        "deterministic": result,
                        "learning": learning,
                        "indicators": indicators,
                        "execution": execution,
                        "observed_at": observed_at,
                        "universe_id": universe.universe_id,
                        "rank": rank,
                        "positions": positions,
                    }
                )
            except Exception as exc:
                self.last_error = (
                    f"{config.strategy_id}/{candidate.instrument_id}: "
                    f"{type(exc).__name__}: {exc}"
                )
                continue

        if not rows:
            return

        for policy in ("minute", "event"):
            for row in rows:
                position = row["positions"][policy]
                row.setdefault("feature_by_policy", {})
                row["feature_by_policy"][policy] = feature_snapshot(
                    candidate=row["candidate"],
                    deterministic=row["deterministic"],
                    learning=row["learning"],
                    indicators=row["indicators"],
                    bars=row["bars"],
                    execution=row["execution"],
                    live_rank=int(row["rank"]),
                    position=position,
                )

        for policy in ("minute", "event"):
            policy_rows = []
            for row in rows:
                copied = dict(row)
                copied["feature_snapshot"] = row["feature_by_policy"][policy]
                policy_rows.append(copied)
            await self._run_policy(
                policy=policy,
                rows=policy_rows,
                config=config,
                repository=repository,
                market_service=market_service,
                events=events,
            )

        # Refresh events after ordinary policy decisions/fills before a possible
        # force-flat retry or session summary.
        events = await self._session_events(
            repository,
            config,
            session_date=universe.session_date,
            now=now,
        )
        await self._force_flat_open_positions(
            rows=rows,
            config=config,
            repository=repository,
            market_service=market_service,
            events=events,
            now=now,
        )
        events = await self._session_events(
            repository,
            config,
            session_date=universe.session_date,
            now=now,
        )
        await self._mark_incomplete_open_trades(
            config=config,
            repository=repository,
            events=events,
            session_date=universe.session_date,
            now=now,
        )
        events = await self._session_events(
            repository,
            config,
            session_date=universe.session_date,
            now=now,
        )
        await self._session_summary(
            config=config,
            repository=repository,
            events=events,
            session_date=universe.session_date,
            now=now,
        )
        events = await self._session_events(
            repository,
            config,
            session_date=universe.session_date,
            now=now,
        )
        await self._comparison_summary(
            config=config,
            repository=repository,
            events=events,
            session_date=universe.session_date,
            now=now,
        )

    async def run_once(self) -> int:
        now = self.now_factory()
        if now.tzinfo is None:
            raise ValueError("ai_shadow_monitor_clock_must_be_timezone_aware")
        now = now.astimezone(timezone.utc)
        repository = self.strategy_repository_factory()
        market_service = self.market_service_factory()
        configs = await asyncio.to_thread(repository.list_configs, active_only=True)
        for config in configs:
            if not _eligible(config):
                continue
            try:
                await self._run_config(
                    config,
                    repository,
                    market_service,
                    now=now,
                )
            except Exception as exc:
                self.last_error = f"{config.strategy_id}: {type(exc).__name__}: {exc}"
                trade_log(
                    "auto_trading",
                    "ai_shadow_monitor_error",
                    strategy_id=config.strategy_id,
                    error_type=type(exc).__name__,
                    detail=str(exc),
                    execution_authority=False,
                )
        self.last_run_at = now
        return self.decision_count

    async def _loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                trade_log(
                    "auto_trading",
                    "ai_shadow_monitor_error",
                    error_type=type(exc).__name__,
                    detail=str(exc),
                    execution_authority=False,
                )
            await asyncio.sleep(self.interval_seconds)

    def diagnostics(self) -> dict[str, object]:
        return {
            "enabled": ai_shadow_monitor_enabled(),
            "running": self._task is not None,
            "interval_seconds": self.interval_seconds,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_error": self.last_error,
            "minute_llm_call_count": self.minute_llm_call_count,
            "event_llm_call_count": self.event_llm_call_count,
            "decision_count": self.decision_count,
            "fill_count": self.fill_count,
            "trade_count": self.trade_count,
            "total_token_count": self.total_token_count,
            "execution_authority": False,
        }


def register_trading_ai_shadow_monitor(gateway: FastAPI) -> TradingAIShadowMonitor:
    existing = getattr(gateway.state, _STATE_KEY, None)
    if isinstance(existing, TradingAIShadowMonitor):
        return existing
    monitor = TradingAIShadowMonitor()
    setattr(gateway.state, _STATE_KEY, monitor)

    async def startup() -> None:
        if ai_shadow_monitor_enabled():
            monitor.start()

    async def shutdown() -> None:
        await monitor.stop()

    gateway.router.add_event_handler("startup", startup)
    gateway.router.add_event_handler("shutdown", shutdown)
    return monitor


__all__ = [
    "TradingAIShadowMonitor",
    "ai_shadow_monitor_enabled",
    "register_trading_ai_shadow_monitor",
]
