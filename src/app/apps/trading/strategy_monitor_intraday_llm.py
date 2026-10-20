"""The intraday LLM review step of the strategy monitor (moved out of the class)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from app.apps.trading.us_equity_calendar import EASTERN as _ET

from .gapper_dataset import GapperCandidate, universe_lineage_id
from .strategies.models import GapPullbackResult
from .strategy_intraday_learning import IntradayLearningSnapshot
from .strategy_intraday_llm import (
    EVENT_BATCH_COOLDOWN_MINUTES,
    FULL_REFRESH_MINUTES,
    IntradayLLMResult,
    SharedIntradayAssessment,
    select_intraday_llm_candidates,
    should_run_intraday_llm_batch,
)

# The monitor imports this module lazily, so importing it here makes no cycle.
from .strategy_monitor import (
    StrategyRunHost,
)
from .strategy_repository import (
    TradingStrategyConfigDocument,
    TradingStrategyRepository,
)
from .trade_logging import trade_log
from .trading_ai_budget import (
    INTRADAY_LLM_LIVE_CONTRACT,
    INTRADAY_LLM_SHADOW_CONTRACT,
    TradingAIBudgetExhausted,
    default_trading_ai_budget,
)


def intraday_llm_contract(config: TradingStrategyConfigDocument) -> str:
    """AUTO PAPER passes read the intraday LLM, so they spend the live budget tier."""

    return INTRADAY_LLM_LIVE_CONTRACT if config.mode == "auto_paper" else INTRADAY_LLM_SHADOW_CONTRACT


async def _record_budget_refusal(
    monitor: StrategyRunHost,
    config: TradingStrategyConfigDocument,
    strategy_repository: TradingStrategyRepository,
    universe,
    *,
    contract_id: str,
    observed_at: datetime,
    detail: str | None,
) -> None:
    """One event per strategy and session, instead of an error on every poll."""

    monitor.intraday_llm_budget_skip_count += 1
    notice = (config.strategy_id, universe.session_date)
    if notice in monitor.intraday_llm_budget_notices:
        return
    monitor.intraday_llm_budget_notices.add(notice)
    await monitor._event(
        strategy_repository,
        config,
        instrument_id="__universe__",
        event_type="intraday_llm_batch",
        state="budget_exhausted",
        reason_code="INTRADAY_LLM_BUDGET_EXHAUSTED",
        observed_at=observed_at,
        payload={
            "universe_id": universe.universe_id,
            "contract_id": contract_id,
            "detail": detail,
            "research_only": True,
            "execution_authority": False,
        },
    )


async def run_intraday_llm(
    monitor: StrategyRunHost,
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
            run_id=monitor.current_run_id,
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
    # A live shadow pass re-freezes its universe under a new id every minute;
    # history belongs to the frozen universe it was built from.
    lineage = universe_lineage_id(universe.universe_id)
    previous_by_instrument: dict[str, dict[str, Any]] = {}
    previous_observed_at_by_instrument: dict[str, datetime] = {}
    last_full_refresh_at_by_instrument: dict[str, datetime] = {}
    previous_batch_at: datetime | None = None
    for event in recent_events:
        payload = event.payload if isinstance(event.payload, dict) else {}
        if universe_lineage_id(str(payload.get("universe_id") or "")) != lineage:
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
    payload_modes: dict[str, Literal["delta", "full"]] = {}
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

    contract_id = intraday_llm_contract(config)
    cache = monitor.intraday_llm_assessments
    keys = {
        candidate.instrument_id: cache.key(candidate.instrument_id, row_observed_at, learning)
        for candidate, _, row_observed_at, learning in selected
    }

    def assess() -> tuple[dict[str, SharedIntradayAssessment], IntradayLLMResult | None, bool]:
        """Reuse what another strategy asked at this bar; ask the model for the rest."""

        with cache.lock:
            shared = {
                instrument_id: entry
                for instrument_id, key in keys.items()
                if (entry := cache.get(key)) is not None
            }
            fresh = [row for row in selected if row[0].instrument_id not in shared]
            if not fresh:
                return shared, None, True
            if not default_trading_ai_budget().can_acquire(contract_id):
                return shared, None, False
            monitor.intraday_llm_call_count += 1
            result = monitor.intraday_llm_analyzer_factory().assess(
                fresh,
                ranks=ranks,
                previous_by_instrument=previous_by_instrument,
                trigger_reasons_by_instrument=trigger_reasons,
                payload_modes_by_instrument=payload_modes,
                contract_id=contract_id,
            )
            requested = {row[0].instrument_id for row in fresh}
            for assessment in result.assessments:
                if assessment.instrument_id in requested:
                    cache.put(
                        keys[assessment.instrument_id],
                        SharedIntradayAssessment(
                            assessment=assessment,
                            provider=result.provider,
                            model=result.model,
                            strategy_id=config.strategy_id,
                            payload_mode=payload_modes.get(assessment.instrument_id, "delta"),
                        ),
                    )
            return shared, result, True

    try:
        shared, result, budget_open = await asyncio.to_thread(assess)
    except TradingAIBudgetExhausted as exc:
        await _record_budget_refusal(
            monitor, config, strategy_repository, universe,
            contract_id=contract_id, observed_at=observed_at, detail=str(exc),
        )
        return
    except Exception as exc:
        monitor.intraday_llm_error_count += 1
        trade_log(
            "auto_trading",
            "intraday_llm_error",
            run_id=monitor.current_run_id,
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
        await monitor._event(
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
    if not budget_open:
        await _record_budget_refusal(
            monitor, config, strategy_repository, universe,
            contract_id=contract_id, observed_at=observed_at, detail=None,
        )
        if not shared:
            return

    entries: dict[str, SharedIntradayAssessment] = dict(shared)
    if result is not None:
        for assessment in result.assessments:
            entries.setdefault(
                assessment.instrument_id,
                SharedIntradayAssessment(
                    assessment=assessment,
                    provider=result.provider,
                    model=result.model,
                    strategy_id=config.strategy_id,
                    payload_mode=payload_modes.get(assessment.instrument_id, "delta"),
                ),
            )

    selected_by_id = {row[0].instrument_id: row for row in selected}
    for instrument_id, entry in entries.items():
        row = selected_by_id.get(instrument_id)
        if row is None:
            continue
        candidate, deterministic, row_observed_at, learning = row
        reused = instrument_id in shared
        persisted = await monitor._event(
            strategy_repository,
            config,
            instrument_id=instrument_id,
            event_type="intraday_llm",
            state=entry.assessment.market_regime,
            reason_code="INTRADAY_LLM_ASSESSMENT",
            observed_at=row_observed_at,
            payload={
                "universe_id": universe.universe_id,
                "universe_discovery_source": universe.discovery_source,
                "morning_discovery_rank": candidate.discovery_rank,
                "live_research_rank": ranks.get(instrument_id),
                "provider": entry.provider,
                "model": entry.model,
                "trigger_reasons": list(
                    trigger_reasons.get(instrument_id, ())
                ),
                "payload_mode": entry.payload_mode,
                # Reused from another strategy's request for the same bar.
                "shared_from_strategy_id": entry.strategy_id if reused else None,
                "deterministic_state": deterministic.state,
                "deterministic_reason_code": deterministic.reason_code,
                # Persist full causal state for future delta construction even
                # when only a compact delta was sent to the provider.
                "source_learning": learning.model_dump(mode="json"),
                "assessment": entry.assessment.model_dump(mode="json"),
                "research_only": True,
                "execution_authority": False,
            },
        )
        monitor.intraday_llm_assessment_count += int(persisted)
        monitor.intraday_llm_shared_assessment_count += int(persisted and reused)

    if result is not None:
        monitor.intraday_llm_input_character_count += result.input_characters
        monitor.intraday_llm_input_token_count += result.input_tokens
        monitor.intraday_llm_output_token_count += result.output_tokens
        monitor.intraday_llm_total_token_count += result.total_tokens
        if result.usage_source == "estimated":
            monitor.intraday_llm_estimated_usage_count += 1
    first = next(iter(entries.values()), None)
    await monitor._event(
        strategy_repository,
        config,
        instrument_id="__universe__",
        event_type="intraday_llm_batch",
        state="completed",
        reason_code="INTRADAY_LLM_BATCH_COMPLETED",
        observed_at=observed_at,
        payload={
            "universe_id": universe.universe_id,
            "provider": result.provider if result is not None else first.provider if first else None,
            "model": result.model if result is not None else first.model if first else None,
            "contract_id": contract_id,
            "model_called": result is not None,
            "requested_instrument_ids": [row[0].instrument_id for row in selected],
            "shared_instrument_ids": sorted(shared),
            "assessment_count": len(entries),
            "top_n": config.config.intraday_llm_top_n,
            "heartbeat_minutes": config.config.intraday_llm_interval_minutes,
            "heartbeat_enabled": heartbeat_enabled,
            "event_cooldown_minutes": EVENT_BATCH_COOLDOWN_MINUTES,
            "full_refresh_minutes": FULL_REFRESH_MINUTES,
            "trigger_reasons": trigger_reasons,
            "payload_modes": payload_modes,
            "token_usage": {
                "source": result.usage_source if result is not None else "shared",
                "input_characters": result.input_characters if result is not None else 0,
                "output_characters": result.output_characters if result is not None else 0,
                "input_tokens": result.input_tokens if result is not None else 0,
                "output_tokens": result.output_tokens if result is not None else 0,
                "total_tokens": result.total_tokens if result is not None else 0,
            },
            "research_only": True,
            "execution_authority": False,
        },
    )
