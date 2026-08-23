from __future__ import annotations

import asyncio
import hashlib
import os
from contextlib import suppress
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Callable
from zoneinfo import ZoneInfo

from fastapi import FastAPI

from .paper import PaperExecutionPolicy
from .providers.errors import ProviderContractError, ProviderDataUnavailableError
from .strategy_backtest import GapPullbackBacktestResult, freeze_backtest_session, run_gap_pullback_backtest
from .strategy_historical_bars import alpaca_historical_session_bars
from .strategy_repository import (
    StrategyEvent,
    TradingStrategyConfigDocument,
    TradingStrategyRepository,
    default_strategy_repository,
)
from .strategy_shadow_universe import resolve_v2_shadow_archive_for_session
from .strategy_v2_qualification import (
    FROZEN_V2_PROFILE_FINGERPRINT,
    V2_PROSPECTIVE_START,
    V2_QUALIFICATION_EVENT_TYPES,
    V2_QUALIFICATION_VERSION,
    V2_REPLAY_VERSION,
    v2_profile_fingerprint,
)
from .trade_logging import trade_log
from .us_equity_calendar import early_close_time, regular_holidays


_ET = ZoneInfo("America/New_York")
_STATE_KEY = "_omnix_trading_strategy_v2_qualification_monitor"
_REPLAY_SPREAD_BPS = Decimal("150")
_REPLAY_INITIAL_CASH = Decimal("100000")
_REPLAY_LOOKBACK_DAYS = 7
_REPLAY_CLOSE_GRACE_MINUTES = 10
BarLoader = Callable[..., dict[str, list[object]]]


def _flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def strategy_v2_qualification_monitor_enabled() -> bool:
    if os.environ.get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return _flag("OMNIX_TRADING_V2_QUALIFICATION_IN_TESTS", "0")
    return _flag("OMNIX_TRADING_V2_QUALIFICATION", "1")


def _interval_seconds() -> float:
    try:
        value = float(os.environ.get("OMNIX_TRADING_V2_QUALIFICATION_INTERVAL_SECONDS", "300"))
    except ValueError:
        value = 300.0
    return max(60.0, value)


def _eligible_strategy(config: TradingStrategyConfigDocument) -> bool:
    return (
        config.enabled
        and config.mode == "shadow"
        and config.config.strategy_version == "2.0.0"
        and v2_profile_fingerprint(config.config) == FROZEN_V2_PROFILE_FINGERPRINT
    )


def _trading_session(session_date: date) -> bool:
    return session_date >= V2_PROSPECTIVE_START and session_date.weekday() < 5 and session_date not in regular_holidays(session_date.year)


def _session_finalized(session_date: date, now: datetime) -> bool:
    if now.tzinfo is None:
        raise ValueError("v2 qualification clock must be timezone-aware")
    now_et = now.astimezone(_ET)
    close = early_close_time(session_date) or time(16, 0)
    finalized = datetime.combine(session_date, close, tzinfo=_ET) + timedelta(minutes=_REPLAY_CLOSE_GRACE_MINUTES)
    return now_et >= finalized


def _event_id(*parts: object) -> tuple[str, str]:
    raw = "|".join(str(part) for part in parts)
    idem = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return idem[:32], idem


def _qualification_events(
    repository: TradingStrategyRepository,
    strategy_id: str,
    *,
    start_time: datetime,
    end_time: datetime,
) -> list[StrategyEvent]:
    if hasattr(repository, "events_by_types_between"):
        return repository.events_by_types_between(
            strategy_id,
            event_types=V2_QUALIFICATION_EVENT_TYPES,
            start_time=start_time,
            end_time=end_time,
            limit=20_000,
        )
    return [
        event
        for event in repository.recent_events(strategy_id, 20_000)
        if event.event_type in V2_QUALIFICATION_EVENT_TYPES
        and start_time <= event.observed_at.astimezone(timezone.utc) < end_time
    ]


def _already_replayed(events: list[StrategyEvent], session_date: date, profile_fingerprint: str) -> bool:
    session = session_date.isoformat()
    return any(
        event.event_type == "v2_shadow_replay_session"
        and event.payload.get("qualification_version") == V2_QUALIFICATION_VERSION
        and event.payload.get("replay_version") == V2_REPLAY_VERSION
        and event.payload.get("profile_fingerprint") == profile_fingerprint
        and event.payload.get("session_date") == session
        and event.payload.get("status") == "completed"
        for event in events
    )


def replay_v2_shadow_session(
    config: TradingStrategyConfigDocument,
    repository: TradingStrategyRepository,
    session_date: date,
    *,
    observed_at: datetime | None = None,
    bar_loader=alpaca_historical_session_bars,
) -> GapPullbackBacktestResult | None:
    """Replay one already-captured prospective SHADOW session without order authority."""

    if not _eligible_strategy(config) or not _trading_session(session_date):
        return None
    observed = observed_at or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise ValueError("v2 qualification replay observed_at must be timezone-aware")
    if not _session_finalized(session_date, observed):
        return None

    profile_fingerprint = v2_profile_fingerprint(config.config)
    events = _qualification_events(
        repository,
        config.strategy_id,
        start_time=datetime.combine(V2_PROSPECTIVE_START, time.min, tzinfo=timezone.utc),
        end_time=observed.astimezone(timezone.utc) + timedelta(seconds=1),
    )
    if _already_replayed(events, session_date, profile_fingerprint):
        return None

    universe = resolve_v2_shadow_archive_for_session(config, repository, session_date=session_date)
    if universe is None:
        return None

    bars_by_instrument = bar_loader(universe.candidates, session_date)
    dataset = freeze_backtest_session(
        session_date=session_date,
        universe=universe,
        bars_by_instrument=bars_by_instrument,
    )
    result = run_gap_pullback_backtest(
        dataset,
        config.config,
        PaperExecutionPolicy(max_volume_participation_pct=Decimal("1")),
        assumed_spread_bps=_REPLAY_SPREAD_BPS,
        max_hold_minutes=config.config.v2_max_hold_minutes,
        max_concurrent_positions=config.risk.max_positions,
        risk_profile=config.risk,
        initial_cash=_REPLAY_INITIAL_CASH,
    )

    observed_utc = observed.astimezone(timezone.utc)
    for index, trade in enumerate(result.trades):
        event_id, idem = _event_id(
            V2_REPLAY_VERSION,
            config.strategy_id,
            session_date.isoformat(),
            profile_fingerprint,
            trade.instrument_id,
            trade.entry_time.astimezone(timezone.utc).isoformat(),
            index,
        )
        repository.append_event(
            StrategyEvent(
                strategy_id=config.strategy_id,
                event_id=event_id,
                run_id=None,
                instrument_id=trade.instrument_id,
                event_type="v2_shadow_replay_trade",
                state="replayed",
                reason_code="V2_SHADOW_REPLAY_TRADE",
                observed_at=observed_utc,
                idempotency_key=idem,
                payload={
                    "qualification_version": V2_QUALIFICATION_VERSION,
                    "replay_version": V2_REPLAY_VERSION,
                    "session_date": session_date.isoformat(),
                    "universe_id": universe.universe_id,
                    "universe_source": "auto_archive_shadow",
                    "universe_fingerprint": universe.source_fingerprint,
                    "profile_fingerprint": profile_fingerprint,
                    "dataset_fingerprint": result.dataset_fingerprint,
                    "assumed_spread_bps": str(_REPLAY_SPREAD_BPS),
                    "execution_policy_version": result.execution_policy_version,
                    "entry_time": trade.entry_time.astimezone(timezone.utc).isoformat(),
                    "exit_time": trade.exit_time.astimezone(timezone.utc).isoformat(),
                    "exit_reason": trade.exit_reason,
                    "r_result": str(trade.r_multiple),
                    "mfe_r": str(trade.mfe_r),
                    "mae_r": str(trade.mae_r),
                    "execution_authority": False,
                },
            )
        )

    session_event_id, session_idem = _event_id(
        V2_REPLAY_VERSION,
        config.strategy_id,
        session_date.isoformat(),
        profile_fingerprint,
        dataset.dataset_fingerprint,
        "session",
    )
    repository.append_event(
        StrategyEvent(
            strategy_id=config.strategy_id,
            event_id=session_event_id,
            run_id=None,
            instrument_id=f"strategy:{config.strategy_id}",
            event_type="v2_shadow_replay_session",
            state="replayed",
            reason_code="V2_SHADOW_REPLAY_COMPLETED",
            observed_at=observed_utc,
            idempotency_key=session_idem,
            payload={
                "qualification_version": V2_QUALIFICATION_VERSION,
                "replay_version": V2_REPLAY_VERSION,
                "session_date": session_date.isoformat(),
                "status": "completed",
                "universe_id": universe.universe_id,
                "universe_source": "auto_archive_shadow",
                "universe_fingerprint": universe.source_fingerprint,
                "profile_fingerprint": profile_fingerprint,
                "dataset_fingerprint": result.dataset_fingerprint,
                "candidate_count": result.summary.candidate_count,
                "trigger_count": result.summary.trigger_count,
                "trade_count": result.summary.trade_count,
                "assumed_spread_bps": str(_REPLAY_SPREAD_BPS),
                "execution_policy_version": result.execution_policy_version,
                "execution_authority": False,
            },
        )
    )
    trade_log(
        "auto_trading",
        "v2_shadow_replay_completed",
        strategy_id=config.strategy_id,
        session_date=session_date,
        universe_id=universe.universe_id,
        profile_fingerprint=profile_fingerprint,
        dataset_fingerprint=result.dataset_fingerprint,
        trade_count=result.summary.trade_count,
        assumed_spread_bps=_REPLAY_SPREAD_BPS,
        execution_authority=False,
    )
    return result


class TradingStrategyV2QualificationMonitor:
    """Evidence-only prospective V2 replay monitor; never creates orders."""

    def __init__(self, *, interval_seconds: float | None = None) -> None:
        self.interval_seconds = interval_seconds or _interval_seconds()
        self._task: asyncio.Task[None] | None = None
        self.last_run_at: datetime | None = None
        self.last_error: str | None = None
        self.replay_count = 0

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
        repository = default_strategy_repository()
        configs = await asyncio.to_thread(repository.list_configs, active_only=False)
        now = datetime.now(timezone.utc)
        replays = 0
        for config in configs:
            if not _eligible_strategy(config):
                continue
            for offset in range(_REPLAY_LOOKBACK_DAYS + 1):
                session_date = now.astimezone(_ET).date() - timedelta(days=offset)
                if not _trading_session(session_date) or not _session_finalized(session_date, now):
                    continue
                try:
                    result = await asyncio.to_thread(
                        replay_v2_shadow_session,
                        config,
                        repository,
                        session_date,
                        observed_at=now,
                    )
                    if result is not None:
                        replays += 1
                except (ProviderContractError, ProviderDataUnavailableError, OSError, ValueError) as exc:
                    self.last_error = f"{config.strategy_id}/{session_date}: {type(exc).__name__}: {exc}"
                    trade_log(
                        "auto_trading",
                        "v2_shadow_replay_error",
                        strategy_id=config.strategy_id,
                        session_date=session_date,
                        error_type=type(exc).__name__,
                        detail=str(exc),
                        execution_authority=False,
                    )
        self.replay_count += replays
        self.last_run_at = datetime.now(timezone.utc)
        return replays

    async def _loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                trade_log(
                    "auto_trading",
                    "v2_shadow_replay_monitor_error",
                    error_type=type(exc).__name__,
                    detail=str(exc),
                    execution_authority=False,
                )
            await asyncio.sleep(self.interval_seconds)


def register_trading_strategy_v2_qualification_monitor(gateway: FastAPI) -> TradingStrategyV2QualificationMonitor:
    existing = getattr(gateway.state, _STATE_KEY, None)
    if isinstance(existing, TradingStrategyV2QualificationMonitor):
        return existing
    monitor = TradingStrategyV2QualificationMonitor()
    setattr(gateway.state, _STATE_KEY, monitor)

    async def startup() -> None:
        if strategy_v2_qualification_monitor_enabled():
            monitor.start()

    async def shutdown() -> None:
        await monitor.stop()

    gateway.router.add_event_handler("startup", startup)
    gateway.router.add_event_handler("shutdown", shutdown)
    return monitor


__all__ = [
    "TradingStrategyV2QualificationMonitor",
    "register_trading_strategy_v2_qualification_monitor",
    "replay_v2_shadow_session",
    "strategy_v2_qualification_monitor_enabled",
]
