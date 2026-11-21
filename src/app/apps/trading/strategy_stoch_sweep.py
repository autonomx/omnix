"""The Stoch arm is read at every 3m bar close, not only when the strategy pass reaches it.

A full strategy pass runs every configuration in turn and takes minutes, so a configuration's
Stoch arm was evaluated about every ten minutes. Its entry is actionable only until the next 3m
bar is final, and its exits are decided at a bar close, so on 2026-11-12 ten of twenty-two entries
since 2026-11-03 were recorded as missed, a 13:51 runner exit was captured at 15:54 and a 15:57
force-flat at 16:03:40, after the bell. During the regular session this monitor reads each
unfinished stock of each Stoch configuration once per 3m bar, as soon as the bar is final, and
captures an entry or an exit with the same event and idempotency key the pass would write, so
the pass then finds it captured. Stocks without an entry are read only while an entry is still
possible; held stocks until the bell. Missed-action records and trade summaries stay with the
pass. Research only: it records evidence and places no order.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.apps.trading.us_equity_calendar import EASTERN as _ET
from app.apps.trading.us_equity_calendar import REGULAR_OPEN, regular_close_time, regular_holidays
from app.runtime.features import FeatureContext

from .monitor_task import ScheduledTradingMonitor, TradingMonitorTask
from .service import TradingMarketDataService, default_market_data_service
from .strategy_monitor import (
    StrategyRunHost,
    _flag,
    _run_id,
    strategy_monitor_owns,
    trading_strategy_monitor_enabled,
)
from .strategy_monitor_candidates import (
    load_candidate_session_bars,
    session_market_service,
    stoch_execution_action_for_snapshot,
)
from .strategy_monitor_stoch_capture import (
    capture_stoch_action,
    capture_stoch_entry,
    hold_stoch_quote_line,
    stoch_session_events,
)
from .strategy_repository import (
    TradingStrategyConfigDocument,
    TradingStrategyRepository,
    default_strategy_repository,
)
from .strategy_shadow_universe import resolve_v2_runtime_archive
from .strategy_stoch_trend_capture import evaluate_stoch_trend_capture
from .trade_logging import trade_log

SWEEP_INTERVAL_SECONDS = 5.0
BAR_SECONDS = 180
# A bar is looked for this long after it closes, so its last minute has time to arrive.
SLOT_GRACE = timedelta(seconds=2)
# A stock whose bar has not arrived by then is left to the next bar (or the pass).
SLOT_RETRY = timedelta(seconds=60)
# Actions after which the arm holds nothing more of the stock.
TERMINAL_STOCH_ACTIONS = frozenset({"range_exit", "runner_exit", "force_flat"})
TERMINAL_STOCH_STATES = frozenset({"range_exited", "trend_exited", "force_flat"})
# States worth reading first: the arm is armed or holds the stock.
_QUIET_STATES = frozenset({"waiting_oversold", "data_gap"})
_STATE_KEY = "_omnix_trading_stoch_sweep"


def stoch_sweep_enabled() -> bool:
    return trading_strategy_monitor_enabled() and _flag("OMNIX_TRADING_STOCH_SWEEP", "1")


def latest_bar_close(now: datetime) -> datetime | None:
    """The end of the latest regular-session 3m bar that should be final now, or None."""
    looked_at = (now - SLOT_GRACE).astimezone(_ET)
    day = looked_at.date()
    if day.weekday() >= 5 or day in regular_holidays(day.year):
        return None
    # An early close (13:00 ET) ends the session's bars early.
    if not REGULAR_OPEN <= now.astimezone(_ET).time() < regular_close_time(day):
        return None
    opened = datetime.combine(day, REGULAR_OPEN, tzinfo=_ET)
    elapsed = int((looked_at - opened).total_seconds())
    if elapsed < BAR_SECONDS:
        return None
    return (opened + timedelta(seconds=elapsed - elapsed % BAR_SECONDS)).astimezone(timezone.utc)


@dataclass
class StochSessionHistory:
    """What the arm has already recorded today, keyed as the pass keys it."""

    entered: set[str] = field(default_factory=set)
    closed: set[str] = field(default_factory=set)
    entry_signals: set[tuple[str, str]] = field(default_factory=set)
    actions: set[tuple[str, str, str]] = field(default_factory=set)

    @property
    def open_positions(self) -> set[str]:
        return self.entered - self.closed


def stoch_session_history(events: list) -> StochSessionHistory:
    history = StochSessionHistory()
    for event in events:
        observed = event.observed_at.astimezone(timezone.utc).isoformat()
        if event.event_type == "stoch_trend_capture_entry":
            history.entered.add(event.instrument_id)
            history.entry_signals.add((event.instrument_id, observed))
            continue
        payload = event.payload if isinstance(event.payload, dict) else {}
        action = payload.get("action")
        if not isinstance(action, str):
            continue
        history.actions.add((event.instrument_id, action, observed))
        if action in TERMINAL_STOCH_ACTIONS:
            history.closed.add(event.instrument_id)
    return history


class TradingStochSweepMonitor(ScheduledTradingMonitor, StrategyRunHost):
    """Reads each unfinished Stoch stock once per 3m bar close and captures its entry or exit."""

    error_event = "stoch_sweep_error"
    # Under one bar: a run cut short keeps the stocks it finished, and the next run goes on.
    timeout_seconds = 170.0

    def __init__(
        self,
        *,
        strategy_repository_factory: Callable[[], TradingStrategyRepository] = default_strategy_repository,
        market_service_factory: Callable[[], TradingMarketDataService] = default_market_data_service,
        now_factory: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        interval_seconds: float = SWEEP_INTERVAL_SECONDS,
    ) -> None:
        StrategyRunHost.__init__(self)
        self.strategy_repository_factory = strategy_repository_factory
        self.market_service_factory = market_service_factory
        self.now_factory = now_factory
        self.interval_seconds = interval_seconds
        self.last_run_at: datetime | None = None
        self.last_slot: datetime | None = None
        self.sweep_count = 0
        self.target_count = 0
        self.read_count = 0
        self.capture_count = 0
        self._session_date: date | None = None
        self._config_slot: dict[str, datetime] = {}
        self._candidate_slot: dict[tuple[str, str], datetime] = {}
        self._last_state: dict[tuple[str, str], str] = {}
        self._finished: set[tuple[str, str]] = set()

    async def run_once(self) -> int:
        from .strategy_runner_parity import runner_owned

        now = self.now_factory()
        self.last_run_at = now
        slot = latest_bar_close(now)
        if slot is None:
            return 0
        self._start_session(now.astimezone(_ET).date())
        strategy_repository = self.strategy_repository_factory()
        configs = await asyncio.to_thread(strategy_repository.list_configs, active_only=True)
        swept = [
            config for config in configs
            if config.config.stoch_trend_capture_enabled
            and not runner_owned(config)
            and strategy_monitor_owns(config)
            and self._config_slot.get(config.strategy_id) != slot
        ]
        if not swept:
            return 0
        self.sweep_count += 1
        self.last_slot = slot
        self.current_run_id = _run_id("stoch-sweep", now)
        market_service = self.market_service_factory()
        captured = 0
        for config in swept:
            captured += await self._sweep_config(config, strategy_repository, market_service, now, slot)
        self.capture_count += captured
        return captured

    def _start_session(self, session_date: date) -> None:
        if self._session_date == session_date:
            return
        self._session_date = session_date
        self._config_slot.clear()
        self._candidate_slot.clear()
        self._last_state.clear()
        self._finished.clear()

    async def _sweep_config(
        self,
        config: TradingStrategyConfigDocument,
        strategy_repository: TradingStrategyRepository,
        market_service: TradingMarketDataService,
        now: datetime,
        slot: datetime,
    ) -> int:
        sid = config.strategy_id
        if config.active_universe_id is not None:
            universe = await asyncio.to_thread(strategy_repository.get_universe, config.active_universe_id)
        else:
            universe = await asyncio.to_thread(resolve_v2_runtime_archive, config, strategy_repository, now=now)
        if universe is None or universe.session_date != now.astimezone(_ET).date():
            self._config_slot[sid] = slot
            return 0
        try:
            events = await stoch_session_events(strategy_repository, config, universe.session_date)
        except Exception as exc:
            # Without the history a capture could repeat one the pass already made.
            self._log("stoch_sweep_history_error", config, error_type=type(exc).__name__, detail=str(exc))
            return 0
        history = stoch_session_history(events)
        entries_open = config.risk.entry_start_et <= slot.astimezone(_ET).time() <= config.risk.last_entry_et
        targets = [
            candidate for candidate in universe.candidates
            if self._candidate_slot.get((sid, candidate.instrument_id)) != slot
            and (sid, candidate.instrument_id) not in self._finished
            and candidate.instrument_id not in history.closed
            and (candidate.instrument_id in history.entered or entries_open)
        ]
        # Stocks the arm holds or is armed on first: their bar decides an action now.
        targets.sort(key=lambda candidate: self._last_state.get((sid, candidate.instrument_id)) in _QUIET_STATES)
        self.target_count = len(targets)
        if not targets:
            self._config_slot[sid] = slot
            return 0
        service = session_market_service(config, market_service, universe, now=now)
        captured = 0
        for candidate in targets:
            key = (sid, candidate.instrument_id)
            try:
                count, done = await self._sweep_candidate(
                    config, strategy_repository, service, universe, candidate, history, slot
                )
            except Exception as exc:
                count, done = 0, self.now_factory() - slot >= SLOT_RETRY
                self._log(
                    "stoch_sweep_candidate_error",
                    config,
                    instrument_id=candidate.instrument_id,
                    error_type=type(exc).__name__,
                    detail=str(exc),
                )
            captured += count
            if done:
                self._candidate_slot[key] = slot
        if all(self._candidate_slot.get((sid, candidate.instrument_id)) == slot for candidate in targets):
            self._config_slot[sid] = slot
        return captured

    async def _sweep_candidate(
        self,
        config: TradingStrategyConfigDocument,
        strategy_repository: TradingStrategyRepository,
        market_service: TradingMarketDataService,
        universe,
        candidate,
        history: StochSessionHistory,
        slot: datetime,
    ) -> tuple[int, bool]:
        """Returns the captures written and whether this stock is done for the slot."""
        now = self.now_factory()
        give_up = now - slot >= SLOT_RETRY
        loaded = await load_candidate_session_bars(
            market_service,
            universe,
            candidate,
            now_utc=now,
            legacy_candidate_contract=(
                not hasattr(universe, "evaluation_time") and not hasattr(candidate, "market_data_complete")
            ),
        )
        if not loaded.current_ready or not loaded.base_bars:
            return 0, give_up
        self.read_count += 1
        snapshot = evaluate_stoch_trend_capture(
            loaded.base_bars,
            entry_start_et=config.risk.entry_start_et,
            last_entry_et=config.risk.last_entry_et,
            force_flat_et=config.risk.force_flat_et,
        )
        key = (config.strategy_id, candidate.instrument_id)
        self._last_state[key] = snapshot.state
        hold_stoch_quote_line(snapshot, candidate.instrument_id, now=now)
        # Until the slot's bar is final the stock is read again; what the tape shows now is acted
        # on as the pass would, and the capture keys keep a later read from repeating it.
        bar_read = snapshot.as_of is not None and snapshot.as_of >= slot
        if snapshot.state in TERMINAL_STOCH_STATES:
            self._finished.add(key)
        captured = 0
        entry_payload = await capture_stoch_entry(
            self,
            config,
            strategy_repository,
            market_service,
            universe=universe,
            candidate=candidate,
            snapshot=snapshot,
            observed_at=snapshot.as_of or loaded.base_bars[-1].end_time,  # as the pass records it
            captured_entry_signals=history.entry_signals,
        )
        if entry_payload is not None:
            history.entered.add(candidate.instrument_id)
            captured += 1
            self._log_capture(config, candidate.instrument_id, "entry", snapshot.entry_signal_time, entry_payload)
        execution_action = stoch_execution_action_for_snapshot(snapshot)
        if execution_action is not None and execution_action[0] != "entry":
            action, action_time = execution_action
            action_key = (candidate.instrument_id, action, action_time.astimezone(timezone.utc).isoformat())
            if action_key not in history.actions:
                payload = await capture_stoch_action(
                    self,
                    config,
                    strategy_repository,
                    market_service,
                    universe_id=universe.universe_id,
                    instrument_id=candidate.instrument_id,
                    binding_id=candidate.binding_id,
                    snapshot=snapshot,
                    action=action,
                    action_time=action_time,
                )
                history.actions.add(action_key)
                if action in TERMINAL_STOCH_ACTIONS:
                    history.closed.add(candidate.instrument_id)
                    self._finished.add(key)
                captured += 1
                self._log_capture(config, candidate.instrument_id, action, action_time, payload)
        return captured, bar_read or give_up or captured > 0

    def _log_capture(
        self,
        config: TradingStrategyConfigDocument,
        instrument_id: str,
        action: str,
        decision_at: datetime | None,
        payload: dict[str, Any],
    ) -> None:
        execution = payload.get("execution")
        self._log(
            "stoch_sweep_capture",
            config,
            instrument_id=instrument_id,
            action=action,
            decision_at=decision_at,
            captured=execution is not None,
            execution_source_time=execution.get("source_time") if isinstance(execution, dict) else None,
        )

    def _log(self, event: str, config: TradingStrategyConfigDocument, **fields: Any) -> None:
        trade_log(
            "auto_trading",
            event,
            run_id=self.current_run_id,
            strategy_id=config.strategy_id,
            research_only=True,
            execution_authority=False,
            **fields,
        )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "enabled": stoch_sweep_enabled(),
            "scheduled": self.scheduled,
            "interval_seconds": self.interval_seconds,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_slot": self.last_slot.isoformat() if self.last_slot else None,
            "last_error": self.last_error,
            "sweep_count": self.sweep_count,
            "target_count": self.target_count,
            "read_count": self.read_count,
            "capture_count": self.capture_count,
            "research_only": True,
            "execution_authority": False,
        }


def create_trading_stoch_sweep_task(context: FeatureContext) -> TradingMonitorTask | None:
    state = context.runtime_state
    if isinstance(getattr(state, _STATE_KEY, None), TradingStochSweepMonitor):
        return None
    monitor = TradingStochSweepMonitor()
    setattr(state, _STATE_KEY, monitor)
    return TradingMonitorTask(name=__name__, monitor=monitor, enabled=stoch_sweep_enabled)


__all__ = [
    "SWEEP_INTERVAL_SECONDS",
    "StochSessionHistory",
    "TradingStochSweepMonitor",
    "create_trading_stoch_sweep_task",
    "latest_bar_close",
    "stoch_session_history",
    "stoch_sweep_enabled",
]
