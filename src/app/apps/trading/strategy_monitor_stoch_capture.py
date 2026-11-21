"""The Stoch arm's quote line and its entry and exit evidence capture. Research only: nothing here places orders."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.apps.trading.us_equity_calendar import EASTERN as _ET

from .held_quote_demand import default_held_quote_demand
from .service import TradingMarketDataService

# The monitor imports its candidate code lazily, so importing it here makes no cycle.
from .strategy_monitor import StrategyRunHost
from .strategy_repository import (
    TradingStrategyConfigDocument,
    TradingStrategyRepository,
)
from .strategy_shadow_execution import observe_shadow_execution
from .strategy_stoch_execution_cost import (
    StochExecutionAction,
    requested_fraction_for_action as stoch_requested_fraction_for_action,
    simulate_stoch_execution,
)
from .strategy_stoch_trend_capture import stoch_trend_capture_risk_decision


# Stoch states in which an entry or exit order may come next: the stock keeps a live
# IBKR quote line, so its fill is priced on the NBBO (owner decision 2026-11-12).
STOCH_QUOTE_LINE_STATES = frozenset({
    "setup_armed",
    "entry_armed",
    "range_active",
    "range_exit_armed",
    "trend_active",
    "trend_partial_armed",
    "trend_runner",
    "trend_exit_armed",
})


def hold_stoch_quote_line(snapshot, instrument_id: str, *, now: datetime) -> bool:
    """Ask the IBKR monitor for the stock's live line while the arm may trade it."""
    if snapshot.state not in STOCH_QUOTE_LINE_STATES:
        return False
    default_held_quote_demand().hold({instrument_id}, now=now)
    return True


async def capture_stoch_action(
    monitor: StrategyRunHost,
    config: TradingStrategyConfigDocument,
    strategy_repository: TradingStrategyRepository,
    market_service: TradingMarketDataService,
    *,
    universe_id: str,
    instrument_id: str,
    binding_id: str | None,
    snapshot,
    action: StochExecutionAction,
    action_time: datetime,
) -> dict[str, Any]:
    """Capture the quote for one Stoch exit action, simulate its fill and record it. Research only."""
    try:
        action_evidence = await asyncio.to_thread(
            observe_shadow_execution,
            market_service,
            instrument_id=instrument_id,
            binding_id=binding_id,
        )
        action_simulation = simulate_stoch_execution(
            action_evidence.execution,
            action=action,
            instrument_id=instrument_id,
            binding_id=binding_id,
            decision_at=action_time,
            requested_fraction=stoch_requested_fraction_for_action(
                action,
                snapshot,
            ),
            reference_price=(
                snapshot.runner_exit_price
                if action == "force_flat"
                else None
            ),
        )
        action_payload = {
            "universe_id": universe_id,
            "policy_version": snapshot.policy_version,
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
            "universe_id": universe_id,
            "policy_version": snapshot.policy_version,
            "action": action,
            "decision_at": action_time,
            "execution": None,
            "execution_simulation": None,
            "detail": f"{type(exc).__name__}: {exc}",
            "research_only": True,
            "execution_authority": False,
        }
    await monitor._event(
        strategy_repository,
        config,
        instrument_id=instrument_id,
        event_type="stoch_trend_execution",
        state=action,
        reason_code="STOCH_EXECUTION_ACTION_CAPTURED",
        observed_at=action_time,
        payload=action_payload,
    )
    return action_payload


async def capture_stoch_entry(
    monitor: StrategyRunHost,
    config: TradingStrategyConfigDocument,
    strategy_repository: TradingStrategyRepository,
    market_service: TradingMarketDataService,
    *,
    universe,
    candidate,
    snapshot,
    observed_at: datetime,
    captured_entry_signals: set[tuple[str, str]],
) -> dict[str, Any] | None:
    """Record a Stoch entry's evidence once per signal; returns the payload written, or None.

    Execution conditions are captured exactly when the first 3m oversold signal becomes
    actionable. A later look must not backfill entry eligibility from changed quotes: once
    the next 3m bar is final, the entry is recorded as missed instead.
    """
    signal_time = snapshot.entry_signal_time
    if signal_time is None:
        return None
    signal_key = (candidate.instrument_id, signal_time.astimezone(timezone.utc).isoformat())
    if signal_key in captured_entry_signals:
        return None
    if snapshot.state == "entry_armed":
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
                    decision_at=signal_time,
                    requested_fraction=Decimal("1"),
                )
                if risk_decision.allowed
                else None
            )
            source_time = entry_evidence.execution.get("source_time")
            capture_lag_seconds = None
            if isinstance(source_time, datetime):
                capture_lag_seconds = (
                    source_time.astimezone(timezone.utc) - signal_time.astimezone(timezone.utc)
                ).total_seconds()
            entry_payload = {
                "universe_id": universe.universe_id,
                "policy_version": snapshot.policy_version,
                "entry_signal_time": signal_time,
                "execution_capture_observed_at": observed_at,
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
                "policy_version": snapshot.policy_version,
                "entry_signal_time": signal_time,
                "execution_capture_observed_at": observed_at,
                "risk_decision": {
                    "allowed": False,
                    "reason_codes": ["STOCH_TREND_EXECUTION_EVIDENCE_ERROR"],
                },
                "execution_simulation": None,
                "detail": f"{type(exc).__name__}: {exc}",
                "research_only": True,
                "execution_authority": False,
            }
    elif snapshot.entry_time is not None:
        # First observed only after the next 3m bar was already final. Never backfill the
        # entry with a later quote: an explicit fail-closed record keeps reconstructed
        # returns from masquerading as prospectively executable trades.
        entry_payload = {
            "universe_id": universe.universe_id,
            "policy_version": snapshot.policy_version,
            "entry_signal_time": signal_time,
            "entry_time": snapshot.entry_time,
            "execution_capture_observed_at": observed_at,
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
    else:
        return None
    # Idempotency is bound to the signal time: the first record of a signal wins, whether
    # captured or missed, and a repeated look at the same armed state adds nothing.
    await monitor._event(
        strategy_repository,
        config,
        instrument_id=candidate.instrument_id,
        event_type="stoch_trend_capture_entry",
        state="entry_evidence",
        reason_code="STOCH_TREND_ENTRY_EVIDENCE_CAPTURED",
        observed_at=signal_time,
        payload=entry_payload,
    )
    captured_entry_signals.add(signal_key)
    return entry_payload


async def stoch_session_events(
    strategy_repository: TradingStrategyRepository,
    config: TradingStrategyConfigDocument,
    session_date,
) -> list:
    """The session's recorded Stoch entries and execution actions for one configuration."""
    session_start_et = datetime(
        session_date.year,
        session_date.month,
        session_date.day,
        tzinfo=_ET,
    )
    session_end_et = session_start_et + timedelta(days=1)
    event_types = ("stoch_trend_capture_entry", "stoch_trend_execution")
    if hasattr(strategy_repository, "events_by_types_between"):
        return await asyncio.to_thread(
            strategy_repository.events_by_types_between,
            config.strategy_id,
            event_types=event_types,
            start_time=session_start_et.astimezone(timezone.utc),
            end_time=session_end_et.astimezone(timezone.utc),
            limit=2_000,
        )
    return [
        event
        for event in await asyncio.to_thread(
            strategy_repository.recent_events,
            config.strategy_id,
            4_000,
        )
        if event.event_type in event_types
        and session_start_et.astimezone(timezone.utc)
        <= event.observed_at.astimezone(timezone.utc)
        < session_end_et.astimezone(timezone.utc)
    ]
