"""Scheduler monitor and provisioning for ``overnight-trading-strategy-shadow``.

SHADOW research only. At the configured decision time it scans the market and
records each arm's picks plus a baseline population as strategy events; after
``label_after_et`` on the next session it labels entries/exits from one-minute
SIP bars and records a per-session scorecard. Events are idempotent, so restarts
and overlapping workers converge. Nothing here places, sizes or routes an order.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable

from app.config.env import environment
from app.config.product import product_name
from app.runtime.features import FeatureContext

from .monitor_task import ScheduledTradingMonitor, TradingMonitorTask
from .paper import PaperAccountCreate
from .paper_repository import TradingPaperRepository
from .strategies.models import OvernightShadowConfig, StrategyRiskProfile
from .strategy_overnight_filings import FILINGS_SOURCE, OvernightFilingsSource
from .strategy_overnight_scan import NEWS_SOURCE, SOCIAL_SOURCE, OvernightMarketData
from .strategy_overnight_shadow import (
    OVERNIGHT_BENCHMARKS,
    OVERNIGHT_TRADING_STRATEGY_ID,
    OvernightCandidate,
    OvernightOutcome,
    OvernightPick,
    label_benchmark,
    label_outcome,
    mid_population,
    news_context,
    population,
    score,
    select_arm_picks,
    split_factors,
)
from .strategy_repository import StrategyEvent, TradingStrategyConfigDocument, TradingStrategyRepository
from .trade_logging import trade_log
from .us_equity_calendar import REGULAR_CLOSE, regular_close_time, regular_holidays
from app.apps.trading.us_equity_calendar import EASTERN as _ET

logger = logging.getLogger(__name__)

_STATE_KEY = "_omnix_overnight_shadow_monitor"
OVERNIGHT_SHADOW_ACCOUNT_ID = "omnix-overnight-shadow"
_ACCOUNT_NAME_SUFFIX = "Overnight SHADOW"
EVENT_PICK = "overnight_pick"
EVENT_POPULATION = "overnight_population"
EVENT_SCAN = "overnight_scan"
EVENT_OUTCOME = "overnight_outcome"
EVENT_SCORECARD = "overnight_scorecard"
EVENT_FILINGS = "overnight_filings"
EVENT_MID_POPULATION = "overnight_mid_population"
_SCAN_INSTRUMENT = "__scan__"
_MID_POPULATION_INSTRUMENT = "__mid_population__"
_FILINGS_INSTRUMENT = "__filings__"
_POPULATION_INSTRUMENT = "__population__"
_SCORECARD_INSTRUMENT = "__scorecard__"
_LABEL_LOOKBACK_SESSIONS = 5


def _flag(name: str, default: str) -> bool:
    return environment().get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def overnight_shadow_monitor_enabled() -> bool:
    if environment().get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return _flag("OMNIX_TRADING_OVERNIGHT_SHADOW_MONITOR_IN_TESTS", "0")
    return _flag("OMNIX_TRADING_OVERNIGHT_SHADOW_MONITOR", "1")


def overnight_shadow_autoprovision_enabled() -> bool:
    if environment().get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return _flag("OMNIX_TRADING_OVERNIGHT_SHADOW_AUTOPROVISION_IN_TESTS", "0")
    return _flag("OMNIX_TRADING_OVERNIGHT_SHADOW_AUTOPROVISION", "1")


# ---------------------------------------------------------------- calendar
def is_session(day: date) -> bool:
    return day.weekday() < 5 and day not in regular_holidays(day.year)


def previous_session(day: date) -> date:
    cursor = day - timedelta(days=1)
    while not is_session(cursor):
        cursor -= timedelta(days=1)
    return cursor


def next_session(day: date) -> date:
    cursor = day + timedelta(days=1)
    while not is_session(cursor):
        cursor += timedelta(days=1)
    return cursor


def _close(day: date) -> time:
    return regular_close_time(day)


# ---------------------------------------------------------------- provisioning
def overnight_shadow_document(account_id: str) -> TradingStrategyConfigDocument:
    return TradingStrategyConfigDocument(
        strategy_id=OVERNIGHT_TRADING_STRATEGY_ID,
        account_id=account_id,
        strategy_kind="overnight_shadow_v1",
        strategy_version="1.0.0",
        mode="shadow",
        active_universe_id=None,
        config=OvernightShadowConfig(),
        risk=StrategyRiskProfile(),
        enabled=True,
    )


def _resolve_account(paper_repository: TradingPaperRepository) -> str:
    accounts = {account.account_id for account in paper_repository.list_accounts(limit=500)}
    if OVERNIGHT_SHADOW_ACCOUNT_ID in accounts:
        return OVERNIGHT_SHADOW_ACCOUNT_ID
    try:
        # SHADOW never places orders; the account only owns the evidence (FK).
        paper_repository.create_account(PaperAccountCreate(
            # Shown in the paper account list, so it carries the visible product name (S-3), not "Omnix" everywhere.
            account_id=OVERNIGHT_SHADOW_ACCOUNT_ID, name=f"{product_name()} {_ACCOUNT_NAME_SUFFIX}",
            initial_cash=Decimal("10000"), commission_bps=Decimal("0"),
        ))
    except Exception:
        # Another worker may have created it first; converge on the durable row.
        if OVERNIGHT_SHADOW_ACCOUNT_ID not in {a.account_id for a in paper_repository.list_accounts(limit=500)}:
            raise
    return OVERNIGHT_SHADOW_ACCOUNT_ID


def provision_overnight_shadow_strategy(
    *,
    strategy_repository: TradingStrategyRepository | None = None,
    paper_repository: TradingPaperRepository | None = None,
) -> str:
    """Create the SHADOW group once. Existing configurations (and archives) are never overwritten."""

    if not overnight_shadow_autoprovision_enabled():
        return "disabled"
    strategy_repo = strategy_repository or TradingStrategyRepository()
    try:
        strategy_repo.get_config(OVERNIGHT_TRADING_STRATEGY_ID)
        return "unchanged"
    except ValueError as exc:
        if str(exc) != "strategy_config_not_found":
            raise
    account_id = _resolve_account(paper_repository or TradingPaperRepository())
    try:
        strategy_repo.create_config(overnight_shadow_document(account_id))
    except Exception:
        try:
            strategy_repo.get_config(OVERNIGHT_TRADING_STRATEGY_ID)
            return "unchanged"
        except ValueError:
            raise
    trade_log("auto_trading", "overnight_shadow_provisioned", strategy_id=OVERNIGHT_TRADING_STRATEGY_ID,
              account_id=account_id, execution_authority=False)
    return "created"


# ---------------------------------------------------------------- events
def _event_id(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:32]


def _event(
    config: TradingStrategyConfigDocument,
    *,
    event_type: str,
    instrument_id: str,
    session_date: date,
    observed_at: datetime,
    payload: dict[str, Any],
    key_suffix: str = "",
    state: str = "recorded",
) -> StrategyEvent:
    key = f"{event_type}:{session_date.isoformat()}:{instrument_id}{key_suffix}"
    return StrategyEvent(
        strategy_id=config.strategy_id,
        event_id=_event_id(config.strategy_id, key),
        run_id=f"overnight:{session_date.isoformat()}",
        instrument_id=instrument_id,
        event_type=event_type,
        state=state,
        observed_at=observed_at,
        idempotency_key=key,
        strategy_revision=config.revision,
        payload=payload,
    )


def _session_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(0), tzinfo=_ET)
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)


def _events(
    repository: TradingStrategyRepository,
    event_types: tuple[str, ...],
    day: date,
    *,
    through: date | None = None,
) -> list[StrategyEvent]:
    """Events of entry session ``day`` (matched by run id) observed from ``day`` through ``through``.

    Picks are observed on the entry session; outcomes and scorecards the next morning or later,
    so labelling lookups pass ``through`` to include those days.
    """

    start, _ = _session_bounds(day)
    _, end = _session_bounds(through or day)
    rows = repository.events_by_types_between(
        OVERNIGHT_TRADING_STRATEGY_ID, event_types=event_types, start_time=start, end_time=end, limit=10_000,
    )
    run_id = f"overnight:{day.isoformat()}"
    return [row for row in rows if row.run_id == run_id]


# ---------------------------------------------------------------- monitor
class OvernightShadowMonitor(ScheduledTradingMonitor):
    error_event = "overnight_shadow_monitor_error"
    # The full-market decision scan takes about a minute when idle and must
    # finish inside the 15:50-16:00 window.
    timeout_seconds = 600.0

    def __init__(
        self,
        *,
        interval_seconds: float = 60.0,
        strategy_repository_factory: Callable[[], TradingStrategyRepository] = TradingStrategyRepository,
        market_data_factory: Callable[[], OvernightMarketData] = OvernightMarketData,
        filings_factory: Callable[[], OvernightFilingsSource] = OvernightFilingsSource,
        now_factory: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.interval_seconds = max(15.0, float(interval_seconds))
        self.strategy_repository_factory = strategy_repository_factory
        self.market_data_factory = market_data_factory
        self.filings_factory = filings_factory
        self.now_factory = now_factory
        self.last_run_at: datetime | None = None
        self.scan_count = 0
        self.label_count = 0
        self.provision_result: str | None = None
        self.provision_error: str | None = None
        # Scheduler cancellation cannot stop a worker thread: a timed-out cycle's
        # scan keeps running, and the next cycle must not start a second one.
        self._work_lock = threading.Lock()

    def error_log_fields(self) -> dict[str, Any]:
        return {"execution_authority": False, "strategy_id": OVERNIGHT_TRADING_STRATEGY_ID}

    def provision(self) -> None:
        try:
            self.provision_result = provision_overnight_shadow_strategy(
                strategy_repository=self.strategy_repository_factory()
            )
            self.provision_error = None
        except Exception as exc:  # startup must not fail the trading feature
            self.provision_error = f"{type(exc).__name__}: {exc}"
            logger.warning("overnight shadow provisioning failed: %s", self.provision_error)

    def _config(self, repository: TradingStrategyRepository) -> TradingStrategyConfigDocument | None:
        try:
            config = repository.get_config(OVERNIGHT_TRADING_STRATEGY_ID)
        except ValueError:
            return None
        if (
            config.strategy_kind != "overnight_shadow_v1"
            or not config.enabled
            or config.mode != "shadow"
            or config.archived_at is not None
        ):
            return None
        return config

    async def run_once(self) -> int:
        now = self.now_factory()
        if now.tzinfo is None:
            raise ValueError("overnight shadow monitor clock must be timezone-aware")
        self.last_run_at = now
        local = now.astimezone(_ET)
        repository = self.strategy_repository_factory()
        config = await asyncio.to_thread(self._config, repository)
        if config is None or not is_session(local.date()):
            return 0
        abandoned = threading.Event()
        try:
            return await asyncio.to_thread(self._run_exclusive, repository, config, now, abandoned)
        except asyncio.CancelledError:
            abandoned.set()
            raise

    def _run_exclusive(
        self,
        repository: TradingStrategyRepository,
        config: TradingStrategyConfigDocument,
        now: datetime,
        abandoned: threading.Event,
    ) -> int:
        if not self._work_lock.acquire(blocking=False):
            return 0  # a cancelled cycle's work is still running in its thread
        try:
            return self._label_due(repository, config, now) + self._scan_due(repository, config, now)
        except Exception as exc:
            if abandoned.is_set():
                # Nothing awaits this thread any more; record the failure here.
                self.record_cycle_error(exc)
            raise
        finally:
            self._work_lock.release()

    # -- 15:50 decision
    def _scan_due(self, repository: TradingStrategyRepository, config: TradingStrategyConfigDocument, now: datetime) -> int:
        settings: OvernightShadowConfig = config.config
        local = now.astimezone(_ET)
        day = local.date()
        if _close(day) != REGULAR_CLOSE:
            return 0  # early close: no entry minute, no picks (matches the backtest)
        if not (settings.decision_et <= local.time() < _close(day)):
            return 0
        if _events(repository, (EVENT_SCAN,), day):
            return 0
        data = self.market_data_factory()
        result = data.scan(day, previous_session(day), settings)
        market, market_error = self._market_context(data, day, settings)
        picks = select_arm_picks(result.candidates, settings)
        pop = population(result.candidates, settings)
        mid = mid_population(result.candidates)
        social = self._social_context(data, pop)
        # One headline request covers both populations; `news.contexts` holds every stock in either.
        news = self._news_context(data, day, pop + [c for c in mid if c.symbol not in {p.symbol for p in pop}], settings)
        late = local.time() >= settings.entry_et
        for arm_id, arm_picks in picks.items():
            for pick in arm_picks:
                repository.append_event(_event(
                    config, event_type=EVENT_PICK, instrument_id=pick.candidate.instrument_id,
                    session_date=day, observed_at=now, key_suffix=f":{arm_id}",
                    payload=pick.model_dump(mode="json") | {"decided_late": late},
                ))
        repository.append_event(_event(
            config, event_type=EVENT_POPULATION, instrument_id=_POPULATION_INSTRUMENT,
            session_date=day, observed_at=now,
            payload={"candidates": [c.model_dump(mode="json") for c in pop]},
        ))
        repository.append_event(_event(
            config, event_type=EVENT_MID_POPULATION, instrument_id=_MID_POPULATION_INSTRUMENT,
            session_date=day, observed_at=now,
            payload={"candidates": [c.model_dump(mode="json") for c in mid], "eligible": result.mid_eligible,
                     "execution_authority": False},
        ))
        # The scan marker is written last: a crash before it lets the next cycle retry;
        # picks and population are idempotent, so a retry cannot duplicate them.
        repository.append_event(_event(
            config, event_type=EVENT_SCAN, instrument_id=_SCAN_INSTRUMENT,
            session_date=day, observed_at=now,
            payload={
                "eligible": result.eligible, "scanned": result.scanned, "candidates": len(result.candidates),
                "population": len(pop), "mid_population": len(mid), "picks": {arm: len(p) for arm, p in picks.items()},
                "decided_late": late, "data_cutoff_et": settings.data_cutoff_et.isoformat(),
                "market": market, "market_error": market_error, "social": social, "news": news,
                "execution_authority": False,
            },
        ))
        self.scan_count += 1
        trade_log("auto_trading", "overnight_shadow_scan", strategy_id=config.strategy_id, session_date=day,
                  picks={arm: [p.candidate.symbol for p in ps] for arm, ps in picks.items()},
                  population=len(pop), execution_authority=False)
        # After the scan marker: the slow EDGAR reads can neither delay nor block the picks. Only
        # filings accepted by ``now`` count, so the record stays point-in-time.
        self._record_filings(repository, config, day, now, pop)
        return 1

    def _record_filings(
        self, repository: TradingStrategyRepository, config: TradingStrategyConfigDocument,
        day: date, now: datetime, pop: list[OvernightCandidate],
    ) -> None:
        payload: dict[str, Any] = {"source": FILINGS_SOURCE, "decided_at": now.isoformat(), "contexts": [],
                                   "truncated": False, "error": None, "execution_authority": False}
        try:
            contexts, truncated = self.filings_factory().contexts([c.symbol for c in pop], decided_at=now)
            payload |= {"contexts": [c.model_dump(mode="json") for c in contexts], "truncated": truncated}
        except Exception as exc:
            logger.warning("overnight shadow filings context failed: %s: %s", type(exc).__name__, exc)
            payload["error"] = f"{type(exc).__name__}: {exc}"
        try:
            repository.append_event(_event(
                config, event_type=EVENT_FILINGS, instrument_id=_FILINGS_INSTRUMENT,
                session_date=day, observed_at=now, payload=payload,
            ))
        except Exception as exc:
            logger.warning("overnight shadow filings event failed: %s: %s", type(exc).__name__, exc)

    @staticmethod
    def _market_context(
        data: OvernightMarketData, day: date, settings: OvernightShadowConfig,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Broad-market context for later research; a failure here never blocks the picks."""

        try:
            return [b.model_dump(mode="json") for b in data.benchmarks(day, previous_session(day), settings)], None
        except Exception as exc:
            logger.warning("overnight shadow market context failed: %s: %s", type(exc).__name__, exc)
            return [], f"{type(exc).__name__}: {exc}"

    @staticmethod
    def _social_context(data: OvernightMarketData, pop: list[OvernightCandidate]) -> dict[str, Any]:
        """Reddit mentions of population stocks (picks are a subset); never blocks the picks.

        ``ranked`` is how many tickers the source listed: a population stock absent from a
        successful fetch had no ranked mentions, which differs from a failed fetch (``error``).
        """

        try:
            mentions = data.social_mentions()
        except Exception as exc:
            logger.warning("overnight shadow social context failed: %s: %s", type(exc).__name__, exc)
            return {"source": SOCIAL_SOURCE, "ranked": None, "mentions": [], "error": f"{type(exc).__name__}: {exc}"}
        symbols = {c.symbol for c in pop}
        return {
            "source": SOCIAL_SOURCE, "ranked": len(mentions),
            "mentions": [m.model_dump(mode="json") for m in mentions if m.symbol in symbols],
            "error": None,
        }

    @staticmethod
    def _news_context(
        data: OvernightMarketData, day: date, pop: list[OvernightCandidate], settings: OvernightShadowConfig,
    ) -> dict[str, Any]:
        """Headlines known at the decision: prior session 16:00 ET to the data cutoff today.

        Every population stock gets a context, so ``articles: 0`` means no headline; a failed fetch
        sets ``error`` and leaves ``contexts`` empty (news unknown, not absent).
        """

        start = datetime.combine(previous_session(day), REGULAR_CLOSE, tzinfo=_ET)
        end = datetime.combine(day, settings.data_cutoff_et, tzinfo=_ET)
        payload: dict[str, Any] = {"source": NEWS_SOURCE, "window_start": start.isoformat(),
                                   "window_end": end.isoformat(), "contexts": [], "error": None}
        if not pop:
            return payload
        try:
            found = data.news([c.symbol for c in pop], start, end)
        except Exception as exc:
            logger.warning("overnight shadow news context failed: %s: %s", type(exc).__name__, exc)
            return payload | {"error": f"{type(exc).__name__}: {exc}"}
        payload["contexts"] = [
            news_context(c.symbol, [h for h in found.get(c.symbol, []) if start <= h.created_at <= end]).model_dump(mode="json")
            for c in pop
        ]
        return payload

    # -- next-morning labelling
    def _label_due(self, repository: TradingStrategyRepository, config: TradingStrategyConfigDocument, now: datetime) -> int:
        settings: OvernightShadowConfig = config.config
        local = now.astimezone(_ET)
        today = local.date()
        if local.time() < settings.label_after_et:
            return 0
        labelled = 0
        entry_day = previous_session(today)
        for _ in range(_LABEL_LOOKBACK_SESSIONS):
            if _events(repository, (EVENT_SCAN,), entry_day) and not _events(
                repository, (EVENT_SCORECARD,), entry_day, through=today
            ):
                self._label_session(repository, config, entry_day, now)
                labelled += 1
            entry_day = previous_session(entry_day)
        return labelled

    def _label_session(
        self, repository: TradingStrategyRepository, config: TradingStrategyConfigDocument, entry_day: date, now: datetime,
    ) -> None:
        settings: OvernightShadowConfig = config.config
        exit_day = next_session(entry_day)
        rows = _events(repository, (EVENT_PICK, EVENT_POPULATION), entry_day)
        picks = [OvernightPick.model_validate({k: v for k, v in r.payload.items() if k != "decided_late"})
                 for r in rows if r.event_type == EVENT_PICK]
        pop = [OvernightCandidate.model_validate(c) for r in rows if r.event_type == EVENT_POPULATION
               for c in r.payload.get("candidates", [])]
        symbols = sorted({p.candidate.symbol for p in picks} | {c.symbol for c in pop} | set(OVERNIGHT_BENCHMARKS))
        data = self.market_data_factory()
        late = data.minute_bars(symbols, datetime.combine(entry_day, time(15, 25), tzinfo=_ET),
                                datetime.combine(entry_day, _close(entry_day), tzinfo=_ET))
        morning = data.minute_bars(symbols, datetime.combine(exit_day, time(4, 0), tzinfo=_ET),
                                   datetime.combine(exit_day, time(9, 46), tzinfo=_ET))
        # Bars are unadjusted: a split taking effect overnight must not read as a gap. A failed
        # lookup fails the cycle, so the session is labelled on a later tick rather than wrongly.
        factors = split_factors(data.splits(symbols, entry_day, exit_day), entry_day, exit_day)

        def outcome(arm_id: str, candidate: OvernightCandidate) -> OvernightOutcome:
            return label_outcome(
                arm_id=arm_id, candidate=candidate, session_date=entry_day, next_session_date=exit_day,
                session_bars=late.get(candidate.symbol, []), next_bars=morning.get(candidate.symbol, []),
                config=settings, session_close=_close(entry_day), next_close=_close(exit_day),
                split_factor=factors.get(candidate.symbol),
            )

        by_arm: dict[str, list[OvernightOutcome]] = {arm.arm_id: [] for arm in settings.arms if arm.enabled}
        for pick in picks:
            result = outcome(pick.arm_id, pick.candidate)
            by_arm.setdefault(pick.arm_id, []).append(result)
            repository.append_event(_event(
                config, event_type=EVENT_OUTCOME, instrument_id=pick.candidate.instrument_id,
                session_date=entry_day, observed_at=now, key_suffix=f":{pick.arm_id}", state=result.status,
                payload=result.model_dump(mode="json"),
            ))
        pop_outcomes = [outcome("population-10pct", c) for c in pop]
        market = [
            label_benchmark(
                symbol=symbol, session_date=entry_day, next_session_date=exit_day,
                session_bars=late.get(symbol, []), next_bars=morning.get(symbol, []),
                config=settings, session_close=_close(entry_day), next_close=_close(exit_day),
                split_factor=factors.get(symbol),
            ).model_dump(mode="json")
            for symbol in OVERNIGHT_BENCHMARKS
        ]
        repository.append_event(_event(
            config, event_type=EVENT_SCORECARD, instrument_id=_SCORECARD_INSTRUMENT,
            session_date=entry_day, observed_at=now, state="labelled",
            payload={
                "entry_session": entry_day.isoformat(), "exit_session": exit_day.isoformat(),
                "arms": [score(arm_id, outs).model_dump(mode="json") for arm_id, outs in sorted(by_arm.items())],
                "population_10pct": score("population-10pct", pop_outcomes).model_dump(mode="json"),
                "market": market,
                "execution_authority": False,
            },
        ))
        self.label_count += 1

    @property
    def running(self) -> bool:
        return self.scheduled


def create_overnight_shadow_monitor_task(context: FeatureContext) -> TradingMonitorTask | None:
    state = context.runtime_state
    if isinstance(getattr(state, _STATE_KEY, None), OvernightShadowMonitor):
        return None
    monitor = OvernightShadowMonitor()
    setattr(state, _STATE_KEY, monitor)
    return TradingMonitorTask(
        name=__name__, monitor=monitor, enabled=overnight_shadow_monitor_enabled, startup=(monitor.provision,),
    )


__all__ = [
    "EVENT_FILINGS",
    "EVENT_MID_POPULATION",
    "EVENT_OUTCOME",
    "EVENT_PICK",
    "EVENT_POPULATION",
    "EVENT_SCAN",
    "EVENT_SCORECARD",
    "OVERNIGHT_SHADOW_ACCOUNT_ID",
    "OvernightShadowMonitor",
    "create_overnight_shadow_monitor_task",
    "overnight_shadow_autoprovision_enabled",
    "overnight_shadow_document",
    "overnight_shadow_monitor_enabled",
    "provision_overnight_shadow_strategy",
]
