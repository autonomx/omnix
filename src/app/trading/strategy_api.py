from __future__ import annotations

import asyncio
import hashlib
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from app.persistence.errors import RevisionConflict

from .catalyst_discovery import discover_yahoo_catalyst_headlines
from .catalyst_evidence import CatalystShadowClassification
from .catalyst_repository import TradingCatalystRepository, default_catalyst_repository
from .catalyst_shadow import generate_catalyst_shadow_classification
from .finviz_gapper_discovery import discover_finviz_gappers
from .gapper_dataset import GapperCandidate, GapperUniverseSnapshot, freeze_gapper_universe
from .gapper_discovery import discover_yahoo_gappers
from .models import MarketBar
from .paper import PaperExecutionPolicy
from .research.fact_repository import default_fact_repository
from .research.outcome_dataset import persist_backtest_trade_outcomes
from .strategies.gap_pullback import evaluate_gap_pullback
from .strategies.models import GapPullbackConfig, GapPullbackResult, StrategyRiskProfile
from .strategy_backtest import GapPullbackBacktestResult, freeze_backtest_session, run_gap_pullback_backtest
from .strategy_finviz_qualification import (
    FINVIZ_V2_PROSPECTIVE_START,
    FINVIZ_V2_QUALIFICATION_EVENT_TYPES,
    FINVIZ_V2_QUALIFICATION_VERSION,
    FinvizV2ProspectiveQualification,
    evaluate_finviz_v2_prospective_qualification,
)
from .strategy_range_backtest import (
    ProgressCallback,
    StrategyRangeBacktestRequest,
    StrategyRangeBacktestResult,
    _trading_dates,
    run_strategy_range_backtest,
)
from .strategy_research_policy import resolve_strategy_research_policy
from .strategy_repository import (
    StrategyEvent,
    StrategyProtection,
    TradingStrategyConfigDocument,
    TradingStrategyRepository,
    default_strategy_repository,
)
from .strategy_v2_qualification import (
    V2_PROSPECTIVE_START,
    V2_QUALIFICATION_EVENT_TYPES,
    V2_QUALIFICATION_VERSION,
    V2ProspectiveQualification,
    evaluate_v2_prospective_qualification,
)
from .trade_logging import trade_log


class StrategyConfigListResponse(BaseModel):
    strategies: list[TradingStrategyConfigDocument]


class StrategyEventListResponse(BaseModel):
    events: list[StrategyEvent]


class StrategyProtectionListResponse(BaseModel):
    protections: list[StrategyProtection]


class StrategyRangeBacktestAcceptedResponse(BaseModel):
    run_id: str
    status: Literal["queued"] = "queued"
    total_sessions: int


class StrategyRangeBacktestProgressResponse(BaseModel):
    run_id: str
    strategy_id: str
    status: Literal["queued", "running", "completed", "failed"]
    completed_sessions: int
    total_sessions: int
    percent: int
    current_session: date | None = None
    error: str | None = None
    result: StrategyRangeBacktestResult | None = None


class V2QualificationReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_note: str = Field(min_length=10, max_length=2_000)


class StrategyEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate: dict[str, object]
    bars: list[MarketBar] = Field(default_factory=list, max_length=1000)
    config: GapPullbackConfig = Field(default_factory=GapPullbackConfig)


class GapperUniverseFreezeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    universe_id: str = Field(min_length=1, max_length=200)
    session_date: date
    evaluation_time: datetime
    discovery_source: Literal["manual", "import", "scanner", "provider", "finviz"] = "import"
    source_locator: str | None = Field(default=None, max_length=2_000)
    source_candidate_symbols: list[str] = Field(default_factory=list, max_length=2_000)
    candidates: list[GapperCandidate] = Field(min_length=1, max_length=2_000)


class YahooGapperDiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    universe_id: str = Field(min_length=1, max_length=200)
    evaluation_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    count: int = Field(default=30, ge=1, le=100)
    minimum_gap_pct: Decimal = Field(default=Decimal("20"), ge=0, le=1000)
    minimum_price: Decimal = Field(default=Decimal("0.50"), gt=0)
    maximum_price: Decimal = Field(default=Decimal("20"), gt=0)


class FinvizGapperDiscoveryRequest(YahooGapperDiscoveryRequest):
    """Same filtering contract, but Finviz determines the source-ranked cohort."""


class GapPullbackBacktestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_date: date
    universe: GapperUniverseSnapshot
    bars_by_instrument: dict[str, list[MarketBar]]
    config: GapPullbackConfig = Field(default_factory=GapPullbackConfig)
    execution_policy: PaperExecutionPolicy = Field(
        default_factory=lambda: PaperExecutionPolicy(max_volume_participation_pct=Decimal("1"))
    )
    risk_profile: StrategyRiskProfile = Field(default_factory=StrategyRiskProfile)
    initial_cash: Decimal = Field(default=Decimal("100000"), gt=0)
    assumed_spread_bps: Decimal = Field(default=Decimal("40"), ge=0, le=10_000)
    max_hold_minutes: int = Field(
        default=390,
        ge=1,
        le=390,
        description="Legacy compatibility field; indicator-based exits do not use elapsed time.",
    )
    max_concurrent_positions: int = Field(default=3, ge=1, le=50)


class StrategyResearchReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str | None = Field(default=None, max_length=200)


class StrategyResearchReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    instrument_id: str
    status: Literal["reviewed", "missing_evidence", "error"]
    classification: CatalystShadowClassification | None = None
    detail: str | None = None


class StrategyResearchReviewResponse(BaseModel):
    strategy_id: str
    universe_id: str
    shadow_only: Literal[True] = True
    reviews: list[StrategyResearchReview]


class StrategyCatalystCaptureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lookback_hours: int = Field(default=72, ge=1, le=168)
    max_items_per_candidate: int = Field(default=8, ge=1, le=25)


class StrategyCatalystCaptureResponse(BaseModel):
    strategy: TradingStrategyConfigDocument
    universe: GapperUniverseSnapshot
    evidence_count: int = Field(ge=0)
    candidates_with_evidence: int = Field(ge=0)
    errors: dict[str, str] = Field(default_factory=dict)


RepositoryFactory = Callable[[], TradingStrategyRepository]
CatalystRepositoryFactory = Callable[[], TradingCatalystRepository]


@dataclass
class _RangeBacktestProgressState:
    run_id: str
    strategy_id: str
    status: Literal["queued", "running", "completed", "failed"]
    completed_sessions: int
    total_sessions: int
    current_session: date | None = None
    error: str | None = None
    result: StrategyRangeBacktestResult | None = None


_RANGE_BACKTEST_PROGRESS: dict[str, _RangeBacktestProgressState] = {}
_RANGE_BACKTEST_PROGRESS_LOCK = threading.Lock()


def _register_range_backtest(run_id: str, strategy_id: str, total_sessions: int) -> None:
    with _RANGE_BACKTEST_PROGRESS_LOCK:
        _RANGE_BACKTEST_PROGRESS[run_id] = _RangeBacktestProgressState(
            run_id=run_id,
            strategy_id=strategy_id,
            status="queued",
            completed_sessions=0,
            total_sessions=total_sessions,
        )


def _update_range_backtest_progress(run_id: str, completed_sessions: int, total_sessions: int, session_date: date) -> None:
    with _RANGE_BACKTEST_PROGRESS_LOCK:
        state = _RANGE_BACKTEST_PROGRESS.get(run_id)
        if state is None:
            return
        state.status = "running"
        state.completed_sessions = completed_sessions
        state.total_sessions = total_sessions
        state.current_session = session_date


def _mark_range_backtest_running(run_id: str) -> None:
    with _RANGE_BACKTEST_PROGRESS_LOCK:
        state = _RANGE_BACKTEST_PROGRESS.get(run_id)
        if state is not None:
            state.status = "running"


def _mark_range_backtest_completed(run_id: str, result: StrategyRangeBacktestResult) -> None:
    with _RANGE_BACKTEST_PROGRESS_LOCK:
        state = _RANGE_BACKTEST_PROGRESS.get(run_id)
        if state is not None:
            state.status = "completed"
            state.completed_sessions = state.total_sessions
            state.current_session = None
            state.result = result


def _mark_range_backtest_failed(run_id: str, error: str) -> None:
    with _RANGE_BACKTEST_PROGRESS_LOCK:
        state = _RANGE_BACKTEST_PROGRESS.get(run_id)
        if state is not None:
            state.status = "failed"
            state.current_session = None
            state.error = error


def _range_backtest_progress_response(run_id: str) -> StrategyRangeBacktestProgressResponse | None:
    with _RANGE_BACKTEST_PROGRESS_LOCK:
        state = _RANGE_BACKTEST_PROGRESS.get(run_id)
        if state is None:
            return None
        percent = 100 if state.status == "completed" else (
            min(99, int(state.completed_sessions * 100 / state.total_sessions))
            if state.total_sessions
            else 0
        )
        return StrategyRangeBacktestProgressResponse(
            run_id=state.run_id,
            strategy_id=state.strategy_id,
            status=state.status,
            completed_sessions=state.completed_sessions,
            total_sessions=state.total_sessions,
            percent=percent,
            current_session=state.current_session,
            error=state.error,
            result=state.result,
        )


def _validate_catalyst_provenance(snapshot: GapperUniverseSnapshot, catalyst_repository: TradingCatalystRepository) -> None:
    evaluation = snapshot.evaluation_time.astimezone(timezone.utc)
    for candidate in snapshot.candidates:
        if not candidate.catalyst_evidence_ids:
            continue
        evidence = catalyst_repository.evidence_by_ids(candidate.instrument_id, candidate.catalyst_evidence_ids)
        for item in evidence:
            if item.published_at > evaluation or item.captured_at > evaluation:
                raise ValueError(
                    "catalyst_evidence_after_universe_freeze:"
                    f"{candidate.instrument_id}:{item.evidence_id}"
                )


def _research_event(
    *,
    strategy_id: str,
    instrument_id: str,
    universe_id: str,
    observed_at: datetime,
    state: str,
    reason_code: str,
    payload: dict[str, object],
) -> StrategyEvent:
    raw = "|".join((strategy_id, instrument_id, universe_id, observed_at.astimezone(timezone.utc).isoformat(), state, reason_code))
    idem = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return StrategyEvent(
        strategy_id=strategy_id,
        event_id=idem[:32],
        instrument_id=instrument_id,
        event_type="research_llm",
        state=state,
        reason_code=reason_code,
        observed_at=observed_at,
        idempotency_key=idem,
        payload={"universe_id": universe_id, "shadow_only": True, **payload},
    )


def _research_universe_id(source_id: str, observed_at: datetime) -> str:
    suffix = f"-research-{observed_at.strftime('%H%M%S')}"
    return source_id[: 200 - len(suffix)] + suffix


def _backtest_run_id(prefix: str, *parts: object) -> str:
    observed_at = datetime.now(timezone.utc)
    digest = hashlib.sha256(
        "|".join(str(part) for part in (prefix, observed_at.isoformat(), *parts)).encode("utf-8")
    ).hexdigest()[:12]
    return f"{prefix}-{observed_at.strftime('%Y%m%dT%H%M%S.%fZ')}-{digest}"


def _v2_qualification_events(
    repository: TradingStrategyRepository,
    strategy_id: str,
    *,
    now: datetime | None = None,
) -> list[StrategyEvent]:
    observed = now or datetime.now(timezone.utc)
    start = datetime(
        V2_PROSPECTIVE_START.year,
        V2_PROSPECTIVE_START.month,
        V2_PROSPECTIVE_START.day,
        tzinfo=timezone.utc,
    )
    end = observed.astimezone(timezone.utc) + timedelta(seconds=1)
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


def _finviz_v2_qualification_events(
    repository: TradingStrategyRepository,
    strategy_id: str,
    *,
    now: datetime | None = None,
) -> list[StrategyEvent]:
    observed = now or datetime.now(timezone.utc)
    start = datetime(
        FINVIZ_V2_PROSPECTIVE_START.year,
        FINVIZ_V2_PROSPECTIVE_START.month,
        FINVIZ_V2_PROSPECTIVE_START.day,
        tzinfo=timezone.utc,
    )
    end = observed.astimezone(timezone.utc) + timedelta(seconds=1)
    if hasattr(repository, "events_by_types_between"):
        return repository.events_by_types_between(
            strategy_id,
            event_types=FINVIZ_V2_QUALIFICATION_EVENT_TYPES,
            start_time=start,
            end_time=end,
            limit=20_000,
        )
    return [
        event
        for event in repository.recent_events(strategy_id, 20_000)
        if event.event_type in FINVIZ_V2_QUALIFICATION_EVENT_TYPES
        and start <= event.observed_at.astimezone(timezone.utc) < end
    ]


def _require_v2_auto_paper_authorized(
    document: TradingStrategyConfigDocument,
    repository: TradingStrategyRepository,
    *,
    now: datetime | None = None,
) -> None:
    if document.mode != "auto_paper" or document.config.strategy_version != "2.0.0":
        return

    if document.config.universe_discovery_source == "finviz":
        if document.active_universe_id is not None:
            raise ValueError("finviz_v2_auto_paper_requires_strategy_owned_archive")
        qualification = evaluate_finviz_v2_prospective_qualification(
            document,
            _finviz_v2_qualification_events(
                repository,
                document.strategy_id,
                now=now,
            ),
        )
        if not qualification.auto_paper_authorized:
            raise ValueError(
                "finviz_v2_auto_paper_requires_reviewed_prospective_qualification"
            )
        return

    qualification = evaluate_v2_prospective_qualification(
        document,
        _v2_qualification_events(repository, document.strategy_id, now=now),
    )
    if not qualification.auto_paper_authorized:
        raise ValueError("v2_auto_paper_requires_reviewed_prospective_qualification")


def _bar_coverage(bars_by_instrument: dict[str, list[MarketBar]]) -> dict[str, dict[str, object]]:
    coverage: dict[str, dict[str, object]] = {}
    for instrument_id, bars in sorted(bars_by_instrument.items()):
        ordered = sorted(bars, key=lambda bar: bar.start_time)
        coverage[instrument_id] = {
            "bar_count": len(ordered),
            "first_start_time": ordered[0].start_time if ordered else None,
            "last_end_time": ordered[-1].end_time if ordered else None,
            "providers": sorted({bar.provider for bar in ordered}),
            "intervals": sorted({bar.interval for bar in ordered}),
        }
    return coverage


async def _execute_range_backtest(
    strategy_id: str,
    request: StrategyRangeBacktestRequest,
    run_id: str,
    repository_factory: RepositoryFactory,
    catalyst_repository_factory: CatalystRepositoryFactory,
    progress_callback: ProgressCallback,
) -> StrategyRangeBacktestResult:
    repository = repository_factory()
    strategy = await asyncio.to_thread(repository.get_config, strategy_id)
    universes = await asyncio.to_thread(
        repository.list_universes,
        start_date=request.start_date,
        end_date=request.end_date,
    )
    catalyst_repository = catalyst_repository_factory()
    for universe in universes:
        _validate_catalyst_provenance(universe, catalyst_repository)
    trade_log(
        "backtest",
        "range_backtest_requested",
        run_id=run_id,
        strategy_id=strategy_id,
        strategy_kind=strategy.strategy_kind,
        strategy_version=strategy.strategy_version,
        strategy_config=strategy.config,
        risk_profile=strategy.risk,
        request=request,
        universe_count=len(universes),
        universes=[
            {
                "universe_id": universe.universe_id,
                "session_date": universe.session_date,
                "evaluation_time": universe.evaluation_time,
                "source_fingerprint": universe.source_fingerprint,
                "candidate_count": len(universe.candidates),
            }
            for universe in universes
        ],
    )
    fact_repository = None

    def range_research_policy_resolver(instrument_id: str, decision_at: datetime):
        nonlocal fact_repository
        if fact_repository is None:
            fact_repository = default_fact_repository()
        return resolve_strategy_research_policy(
            strategy_version=strategy.config.strategy_version,
            instrument_id=instrument_id,
            decision_at=decision_at,
            fact_repository=fact_repository,
        )

    result = await asyncio.to_thread(
        run_strategy_range_backtest,
        strategy,
        universes,
        request,
        research_policy_resolver=range_research_policy_resolver,
        progress_callback=progress_callback,
    )
    for day in result.days:
        trade_log(
            "backtest",
            "range_backtest_day",
            run_id=run_id,
            strategy_id=strategy_id,
            day=day,
        )
        if day.result is not None and day.result.candidate_decisions:
            try:
                fact_repository = fact_repository or default_fact_repository()
                captured = await asyncio.to_thread(
                    persist_backtest_trade_outcomes,
                    strategy_id=strategy_id,
                    strategy_version=strategy.config.strategy_version,
                    session_date=day.session_date,
                    trades=day.result.trades,
                    candidate_decisions=day.result.candidate_decisions,
                    market_fidelity=(
                        "captured_point_in_time" if day.universe_origin == "captured"
                        else "reconstructed_current_listings_iex"
                    ),
                    fact_repository=fact_repository,
                    reward_multiple=strategy.config.reward_multiple,
                )
                trade_log(
                    "backtest",
                    "range_research_outcomes_captured",
                    run_id=run_id,
                    strategy_id=strategy_id,
                    session_date=day.session_date,
                    count=captured,
                )
            except Exception as exc:
                trade_log(
                    "backtest",
                    "research_outcome_capture_error",
                    run_id=run_id,
                    strategy_id=strategy_id,
                    session_date=day.session_date,
                    error_type=type(exc).__name__,
                    detail=str(exc),
                )
    trade_log(
        "backtest",
        "range_backtest_completed",
        run_id=run_id,
        strategy_id=strategy_id,
        result=result.model_dump(mode="json", exclude={"days"}),
    )
    return result


def create_trading_strategy_router(
    repository_factory: RepositoryFactory = default_strategy_repository,
    catalyst_repository_factory: CatalystRepositoryFactory = default_catalyst_repository,
) -> APIRouter:
    router = APIRouter(prefix="/api/trading/strategies", tags=["trading-strategies"])

    @router.get("", response_model=StrategyConfigListResponse)
    async def list_strategies(active_only: bool = Query(default=False)):
        return StrategyConfigListResponse(
            strategies=await asyncio.to_thread(repository_factory().list_configs, active_only=active_only)
        )

    @router.post("", response_model=TradingStrategyConfigDocument, status_code=201)
    async def create_strategy(document: TradingStrategyConfigDocument):
        try:
            repository = repository_factory()
            _require_v2_auto_paper_authorized(document, repository)
            return await asyncio.to_thread(repository.create_config, document)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/backtest/gap-pullback", response_model=GapPullbackBacktestResult)
    async def backtest_gap_pullback(request: GapPullbackBacktestRequest):
        run_id = _backtest_run_id("backtest", request.session_date, request.universe.universe_id)
        trade_log(
            "backtest",
            "backtest_requested",
            run_id=run_id,
            session_date=request.session_date,
            universe_id=request.universe.universe_id,
            universe_evaluation_time=request.universe.evaluation_time,
            universe_source_fingerprint=request.universe.source_fingerprint,
            candidate_count=len(request.universe.candidates),
            bar_coverage=_bar_coverage(request.bars_by_instrument),
            strategy_config=request.config,
            execution_policy=request.execution_policy,
            risk_profile=request.risk_profile,
            initial_cash=request.initial_cash,
            assumed_spread_bps=request.assumed_spread_bps,
            max_hold_minutes=request.max_hold_minutes,
            max_concurrent_positions=request.max_concurrent_positions,
        )
        try:
            _validate_catalyst_provenance(request.universe, catalyst_repository_factory())
            dataset = await asyncio.to_thread(
                freeze_backtest_session,
                session_date=request.session_date,
                universe=request.universe,
                bars_by_instrument=request.bars_by_instrument,
            )
            trade_log(
                "backtest",
                "backtest_dataset_frozen",
                run_id=run_id,
                session_date=request.session_date,
                universe_id=request.universe.universe_id,
                dataset_fingerprint=dataset.dataset_fingerprint,
                candidate_count=len(dataset.universe.candidates),
                bar_counts={
                    instrument_id: len(bars)
                    for instrument_id, bars in sorted(dataset.bars_by_instrument.items())
                },
            )
            fact_repository = None

            def research_policy_resolver(instrument_id: str, decision_at: datetime):
                nonlocal fact_repository
                if fact_repository is None:
                    fact_repository = default_fact_repository()
                return resolve_strategy_research_policy(
                    strategy_version=request.config.strategy_version,
                    instrument_id=instrument_id,
                    decision_at=decision_at,
                    fact_repository=fact_repository,
                )

            result = await asyncio.to_thread(
                run_gap_pullback_backtest,
                dataset,
                request.config,
                request.execution_policy,
                assumed_spread_bps=request.assumed_spread_bps,
                max_hold_minutes=request.max_hold_minutes,
                max_concurrent_positions=request.max_concurrent_positions,
                risk_profile=request.risk_profile,
                initial_cash=request.initial_cash,
                research_policy_resolver=research_policy_resolver,
            )
            try:
                fact_repository = fact_repository or default_fact_repository()
                captured = await asyncio.to_thread(
                    persist_backtest_trade_outcomes,
                    strategy_id=request.config.strategy_id,
                    strategy_version=request.config.strategy_version,
                    session_date=request.session_date,
                    trades=result.trades,
                    candidate_decisions=result.candidate_decisions,
                    market_fidelity="captured_point_in_time",
                    fact_repository=fact_repository,
                    reward_multiple=request.config.reward_multiple,
                )
                trade_log("backtest", "research_outcomes_captured", run_id=run_id, count=captured)
            except Exception as exc:
                trade_log("backtest", "research_outcome_capture_error", run_id=run_id, error_type=type(exc).__name__, detail=str(exc))
            trade_log(
                "backtest",
                "backtest_completed",
                run_id=run_id,
                session_date=request.session_date,
                universe_id=request.universe.universe_id,
                dataset_fingerprint=result.dataset_fingerprint,
                strategy_id=result.strategy_id,
                strategy_version=result.strategy_version,
                execution_policy_version=result.execution_policy_version,
                initial_cash=result.initial_cash,
                risk_policy=result.risk_policy,
                summary=result.summary,
                trades=list(result.trades),
            )
            return result
        except ValueError as exc:
            trade_log(
                "backtest",
                "backtest_failed",
                run_id=run_id,
                session_date=request.session_date,
                universe_id=request.universe.universe_id,
                error_type=type(exc).__name__,
                detail=str(exc),
            )
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/universes/discover-yahoo", response_model=GapperUniverseSnapshot, status_code=201)
    async def discover_yahoo_universe(request: YahooGapperDiscoveryRequest):
        try:
            if request.maximum_price <= request.minimum_price:
                raise ValueError("maximum_price must exceed minimum_price")
            snapshot = await asyncio.to_thread(
                discover_yahoo_gappers,
                universe_id=request.universe_id,
                evaluation_time=request.evaluation_time,
                count=request.count,
                minimum_gap_pct=request.minimum_gap_pct,
                minimum_price=request.minimum_price,
                maximum_price=request.maximum_price,
            )
            return await asyncio.to_thread(repository_factory().save_universe, snapshot)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/universes/discover-finviz", response_model=GapperUniverseSnapshot, status_code=201)
    async def discover_finviz_universe(request: FinvizGapperDiscoveryRequest):
        try:
            if request.maximum_price <= request.minimum_price:
                raise ValueError("maximum_price must exceed minimum_price")
            snapshot = await asyncio.to_thread(
                discover_finviz_gappers,
                universe_id=request.universe_id,
                evaluation_time=request.evaluation_time,
                count=request.count,
                minimum_gap_pct=request.minimum_gap_pct,
                minimum_price=request.minimum_price,
                maximum_price=request.maximum_price,
            )
            return await asyncio.to_thread(repository_factory().save_universe, snapshot)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/universes/freeze", response_model=GapperUniverseSnapshot, status_code=201)
    async def freeze_universe(request: GapperUniverseFreezeRequest):
        try:
            snapshot = await asyncio.to_thread(
                freeze_gapper_universe,
                universe_id=request.universe_id,
                session_date=request.session_date,
                evaluation_time=request.evaluation_time,
                discovery_source=request.discovery_source,
                source_locator=request.source_locator,
                source_candidate_symbols=request.source_candidate_symbols,
                candidates=request.candidates,
            )
            _validate_catalyst_provenance(snapshot, catalyst_repository_factory())
            return await asyncio.to_thread(repository_factory().save_universe, snapshot)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/universes", response_model=GapperUniverseSnapshot, status_code=201)
    async def save_universe(snapshot: GapperUniverseSnapshot):
        try:
            validated = await asyncio.to_thread(
                freeze_gapper_universe,
                universe_id=snapshot.universe_id,
                session_date=snapshot.session_date,
                evaluation_time=snapshot.evaluation_time,
                discovery_source=snapshot.discovery_source,
                source_locator=snapshot.source_locator,
                source_candidate_symbols=snapshot.source_candidate_symbols,
                candidates=snapshot.candidates,
            )
            if validated.source_fingerprint != snapshot.source_fingerprint:
                raise ValueError("gapper_universe_fingerprint_mismatch")
            _validate_catalyst_provenance(snapshot, catalyst_repository_factory())
            return await asyncio.to_thread(repository_factory().save_universe, snapshot)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/universes/{universe_id}", response_model=GapperUniverseSnapshot)
    async def get_universe(universe_id: str):
        try:
            return await asyncio.to_thread(repository_factory().get_universe, universe_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/evaluate/gap-pullback", response_model=GapPullbackResult, include_in_schema=True)
    async def evaluate_strategy(request: StrategyEvaluationRequest):
        try:
            candidate = GapperCandidate.model_validate(request.candidate)
            return await asyncio.to_thread(evaluate_gap_pullback, candidate, request.bars, request.config)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/{strategy_id}/v2/qualification", response_model=V2ProspectiveQualification)
    async def get_v2_qualification(strategy_id: str) -> V2ProspectiveQualification:
        try:
            repository = repository_factory()
            strategy = await asyncio.to_thread(repository.get_config, strategy_id)
            if strategy.config.strategy_version != "2.0.0":
                raise ValueError("v2_qualification_requires_strategy_version_2_0_0")
            events = await asyncio.to_thread(_v2_qualification_events, repository, strategy_id)
            return await asyncio.to_thread(evaluate_v2_prospective_qualification, strategy, events)
        except ValueError as exc:
            status = 404 if str(exc) == "strategy_config_not_found" else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @router.post("/{strategy_id}/v2/qualification/review", response_model=V2ProspectiveQualification)
    async def review_v2_qualification(
        strategy_id: str,
        request: V2QualificationReviewRequest,
    ) -> V2ProspectiveQualification:
        try:
            note = " ".join(request.review_note.split()).strip()
            if len(note) < 10:
                raise ValueError("v2_qualification_review_note_too_short")
            repository = repository_factory()
            strategy = await asyncio.to_thread(repository.get_config, strategy_id)
            if strategy.config.strategy_version != "2.0.0":
                raise ValueError("v2_qualification_requires_strategy_version_2_0_0")
            events = await asyncio.to_thread(_v2_qualification_events, repository, strategy_id)
            qualification = await asyncio.to_thread(
                evaluate_v2_prospective_qualification, strategy, events
            )
            if qualification.auto_paper_authorized:
                return qualification
            if not qualification.qualified:
                raise ValueError("v2_prospective_qualification_not_met")
            observed_at = datetime.now(timezone.utc)
            raw = "|".join((
                "v2-promotion-review",
                strategy_id,
                qualification.current_profile_fingerprint,
                qualification.evidence_fingerprint,
            ))
            idem = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            review_event = StrategyEvent(
                strategy_id=strategy_id,
                event_id=idem[:32],
                instrument_id=f"strategy:{strategy_id}",
                event_type="v2_promotion_review",
                state="qualification_reviewed",
                reason_code="V2_PROMOTION_REVIEW_APPROVED",
                observed_at=observed_at,
                idempotency_key=idem,
                payload={
                    "qualification_version": V2_QUALIFICATION_VERSION,
                    "profile_fingerprint": qualification.current_profile_fingerprint,
                    "evidence_fingerprint": qualification.evidence_fingerprint,
                    "approved_evidence_fingerprint": qualification.evidence_fingerprint,
                    "matched_eligible_trade_count": qualification.matched_eligible_trade_count,
                    "distinct_sessions": qualification.distinct_sessions,
                    "distinct_symbols": qualification.distinct_symbols,
                    "execution_match_rate": (
                        str(qualification.execution_match_rate)
                        if qualification.execution_match_rate is not None
                        else None
                    ),
                    "expectancy_r": (
                        str(qualification.expectancy_r)
                        if qualification.expectancy_r is not None
                        else None
                    ),
                    "one_sided_90_lcb_r": (
                        str(qualification.one_sided_90_lcb_r)
                        if qualification.one_sided_90_lcb_r is not None
                        else None
                    ),
                    "max_drawdown_r": (
                        str(qualification.max_drawdown_r)
                        if qualification.max_drawdown_r is not None
                        else None
                    ),
                    "approved": True,
                    "review_note": note,
                    "execution_authority": False,
                },
            )
            await asyncio.to_thread(repository.append_event, review_event)
            return await asyncio.to_thread(
                evaluate_v2_prospective_qualification,
                strategy,
                [*events, review_event],
            )
        except ValueError as exc:
            status = 404 if str(exc) == "strategy_config_not_found" else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @router.get(
        "/{strategy_id}/finviz/qualification",
        response_model=FinvizV2ProspectiveQualification,
    )
    async def get_finviz_v2_qualification(
        strategy_id: str,
    ) -> FinvizV2ProspectiveQualification:
        try:
            repository = repository_factory()
            strategy = await asyncio.to_thread(repository.get_config, strategy_id)
            if strategy.config.strategy_version != "2.0.0":
                raise ValueError(
                    "finviz_v2_qualification_requires_strategy_version_2_0_0"
                )
            if strategy.config.universe_discovery_source != "finviz":
                raise ValueError("finviz_v2_qualification_requires_finviz_discovery")
            events = await asyncio.to_thread(
                _finviz_v2_qualification_events, repository, strategy_id
            )
            return await asyncio.to_thread(
                evaluate_finviz_v2_prospective_qualification,
                strategy,
                events,
            )
        except ValueError as exc:
            status = 404 if str(exc) == "strategy_config_not_found" else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @router.post(
        "/{strategy_id}/finviz/qualification/review",
        response_model=FinvizV2ProspectiveQualification,
    )
    async def review_finviz_v2_qualification(
        strategy_id: str,
        request: V2QualificationReviewRequest,
    ) -> FinvizV2ProspectiveQualification:
        try:
            note = " ".join(request.review_note.split()).strip()
            if len(note) < 10:
                raise ValueError("finviz_v2_qualification_review_note_too_short")
            repository = repository_factory()
            strategy = await asyncio.to_thread(repository.get_config, strategy_id)
            if strategy.config.strategy_version != "2.0.0":
                raise ValueError(
                    "finviz_v2_qualification_requires_strategy_version_2_0_0"
                )
            if strategy.config.universe_discovery_source != "finviz":
                raise ValueError("finviz_v2_qualification_requires_finviz_discovery")

            events = await asyncio.to_thread(
                _finviz_v2_qualification_events, repository, strategy_id
            )
            qualification = await asyncio.to_thread(
                evaluate_finviz_v2_prospective_qualification,
                strategy,
                events,
            )
            if qualification.auto_paper_authorized:
                return qualification
            if not qualification.qualified:
                raise ValueError("finviz_v2_prospective_qualification_not_met")

            observed_at = datetime.now(timezone.utc)
            raw = "|".join(
                (
                    "finviz-v2-promotion-review",
                    strategy_id,
                    qualification.current_profile_fingerprint,
                    qualification.evidence_fingerprint,
                )
            )
            idem = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            review_event = StrategyEvent(
                strategy_id=strategy_id,
                event_id=idem[:32],
                instrument_id=f"strategy:{strategy_id}",
                event_type="finviz_v2_promotion_review",
                state="qualification_reviewed",
                reason_code="FINVIZ_V2_PROMOTION_REVIEW_APPROVED",
                observed_at=observed_at,
                idempotency_key=idem,
                payload={
                    "qualification_version": FINVIZ_V2_QUALIFICATION_VERSION,
                    "profile_fingerprint": qualification.current_profile_fingerprint,
                    "evidence_fingerprint": qualification.evidence_fingerprint,
                    "approved": True,
                    "review_note": note,
                    "execution_authority": False,
                },
            )
            await asyncio.to_thread(repository.append_event, review_event)
            return await asyncio.to_thread(
                evaluate_finviz_v2_prospective_qualification,
                strategy,
                [*events, review_event],
            )
        except ValueError as exc:
            status = 404 if str(exc) == "strategy_config_not_found" else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @router.get("/{strategy_id}", response_model=TradingStrategyConfigDocument)
    async def get_strategy(strategy_id: str):
        try:
            return await asyncio.to_thread(repository_factory().get_config, strategy_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.put("/{strategy_id}", response_model=TradingStrategyConfigDocument)
    async def update_strategy(strategy_id: str, document: TradingStrategyConfigDocument, if_match: int = Header(alias="If-Match", ge=1)):
        try:
            repository = repository_factory()
            _require_v2_auto_paper_authorized(document, repository)
            return await asyncio.to_thread(
                repository.update_config,
                strategy_id,
                document,
                expected_revision=if_match,
            )
        except RevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.delete("/{strategy_id}", status_code=204)
    async def delete_strategy(
        strategy_id: str,
        if_match: int = Header(alias="If-Match", ge=1),
    ) -> Response:
        try:
            await asyncio.to_thread(
                repository_factory().delete_config,
                strategy_id,
                expected_revision=if_match,
            )
            return Response(status_code=204)
        except RevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            status = 404 if str(exc) == "strategy_config_not_found" else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @router.post(
        "/{strategy_id}/backtest/range",
        response_model=StrategyRangeBacktestAcceptedResponse,
        status_code=202,
    )
    async def backtest_strategy_range(
        strategy_id: str,
        request: StrategyRangeBacktestRequest,
    ) -> StrategyRangeBacktestAcceptedResponse:
        run_id = _backtest_run_id("range", strategy_id, request.start_date, request.end_date)
        try:
            total_sessions = len(_trading_dates(request.start_date, request.end_date))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if total_sessions > request.max_sessions:
            raise HTTPException(
                status_code=422,
                detail=f"backtest_session_limit_exceeded:{total_sessions}>{request.max_sessions}",
            )

        _register_range_backtest(run_id, strategy_id, total_sessions)

        async def execute() -> None:
            _mark_range_backtest_running(run_id)
            try:
                result = await _execute_range_backtest(
                    strategy_id,
                    request,
                    run_id,
                    repository_factory,
                    catalyst_repository_factory,
                    lambda completed, total, session_date: _update_range_backtest_progress(
                        run_id,
                        completed,
                        total,
                        session_date,
                    ),
                )
            except Exception as exc:
                trade_log(
                    "backtest",
                    "range_backtest_failed",
                    run_id=run_id,
                    strategy_id=strategy_id,
                    start_date=request.start_date,
                    end_date=request.end_date,
                    error_type=type(exc).__name__,
                    detail=str(exc),
                )
                _mark_range_backtest_failed(run_id, str(exc))
                return
            _mark_range_backtest_completed(run_id, result)

        asyncio.create_task(execute())
        return StrategyRangeBacktestAcceptedResponse(
            run_id=run_id,
            total_sessions=total_sessions,
        )

    @router.get(
        "/{strategy_id}/backtest/range/{run_id}",
        response_model=StrategyRangeBacktestProgressResponse,
    )
    async def get_backtest_range_progress(
        strategy_id: str,
        run_id: str,
    ) -> StrategyRangeBacktestProgressResponse:
        progress = _range_backtest_progress_response(run_id)
        if progress is None or progress.strategy_id != strategy_id:
            raise HTTPException(status_code=404, detail="backtest_run_not_found")
        return progress

    @router.post("/{strategy_id}/research/capture-yahoo", response_model=StrategyCatalystCaptureResponse)
    async def capture_yahoo_research(strategy_id: str, request: StrategyCatalystCaptureRequest):
        try:
            strategy_repository = repository_factory()
            config = await asyncio.to_thread(strategy_repository.get_config, strategy_id)
            if config.mode == "auto_paper":
                raise ValueError("pause_auto_paper_before_research_capture")
            if not config.active_universe_id:
                raise ValueError("strategy_has_no_active_universe")
            source = await asyncio.to_thread(strategy_repository.get_universe, config.active_universe_id)
            catalyst_repository = catalyst_repository_factory()
            capture_started_at = datetime.now(timezone.utc)
            evidence_count = 0
            errors: dict[str, str] = {}
            enriched: list[GapperCandidate] = []
            for candidate in source.candidates:
                symbol = candidate.instrument_id.split(":")[-1]
                try:
                    evidence = await asyncio.to_thread(
                        discover_yahoo_catalyst_headlines,
                        instrument_id=candidate.instrument_id,
                        symbol=symbol,
                        evaluation_time=capture_started_at,
                        lookback_hours=request.lookback_hours,
                        max_items=request.max_items_per_candidate,
                    )
                except Exception as exc:
                    errors[candidate.instrument_id] = f"{type(exc).__name__}: {exc}"
                    evidence = ()
                for item in evidence:
                    await asyncio.to_thread(catalyst_repository.save_evidence, item)
                evidence_count += len(evidence)
                ids = tuple(dict.fromkeys((*candidate.catalyst_evidence_ids, *(item.evidence_id for item in evidence))))
                flags = tuple(sorted(set(candidate.dilution_flags).union(*(set(item.dilution_flags) for item in evidence))))
                evidence_times = dict(candidate.evidence_observed_at)
                for item in evidence:
                    evidence_times[f"catalyst:{item.evidence_id}"] = item.captured_at
                enriched.append(
                    candidate.model_copy(
                        update={
                            "catalyst_evidence_ids": ids,
                            "dilution_flags": flags,
                            "evidence_observed_at": evidence_times,
                        }
                    )
                )

            freeze_time = datetime.now(timezone.utc)
            snapshot = freeze_gapper_universe(
                universe_id=_research_universe_id(source.universe_id, freeze_time),
                session_date=source.session_date,
                evaluation_time=freeze_time,
                discovery_source="import",
                candidates=enriched,
            )
            _validate_catalyst_provenance(snapshot, catalyst_repository)
            snapshot = await asyncio.to_thread(strategy_repository.save_universe, snapshot)
            updated_document = config.model_copy(update={"active_universe_id": snapshot.universe_id})
            updated = await asyncio.to_thread(
                strategy_repository.update_config,
                strategy_id,
                updated_document,
                expected_revision=config.revision,
            )
            return StrategyCatalystCaptureResponse(
                strategy=updated,
                universe=snapshot,
                evidence_count=evidence_count,
                candidates_with_evidence=sum(bool(item.catalyst_evidence_ids) for item in snapshot.candidates),
                errors=errors,
            )
        except RevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/{strategy_id}/research/llm-review", response_model=StrategyResearchReviewResponse)
    async def run_llm_research(strategy_id: str, request: StrategyResearchReviewRequest):
        try:
            repository = repository_factory()
            config = await asyncio.to_thread(repository.get_config, strategy_id)
            if not config.active_universe_id:
                raise ValueError("strategy_has_no_active_universe")
            universe = await asyncio.to_thread(repository.get_universe, config.active_universe_id)
            catalyst_repository = catalyst_repository_factory()
            reviews: list[StrategyResearchReview] = []
            for candidate in universe.candidates:
                observed_at = datetime.now(timezone.utc)
                if not candidate.catalyst_evidence_ids:
                    review = StrategyResearchReview(
                        instrument_id=candidate.instrument_id,
                        status="missing_evidence",
                        detail="No timestamped catalyst evidence attached to frozen candidate.",
                    )
                    await asyncio.to_thread(
                        repository.append_event,
                        _research_event(
                            strategy_id=strategy_id,
                            instrument_id=candidate.instrument_id,
                            universe_id=universe.universe_id,
                            observed_at=observed_at,
                            state="research_missing",
                            reason_code="CATALYST_EVIDENCE_MISSING",
                            payload={"detail": review.detail or ""},
                        ),
                    )
                    reviews.append(review)
                    continue
                try:
                    evidence = await asyncio.to_thread(
                        catalyst_repository.evidence_by_ids,
                        candidate.instrument_id,
                        candidate.catalyst_evidence_ids,
                    )
                    classification = await asyncio.to_thread(
                        generate_catalyst_shadow_classification,
                        evidence,
                        model=request.model,
                    )
                    await asyncio.to_thread(
                        repository.append_event,
                        _research_event(
                            strategy_id=strategy_id,
                            instrument_id=candidate.instrument_id,
                            universe_id=universe.universe_id,
                            observed_at=observed_at,
                            state="research_reviewed",
                            reason_code="LLM_SHADOW_REVIEW_COMPLETE",
                            payload={"classification": classification.model_dump(mode="json")},
                        ),
                    )
                    reviews.append(
                        StrategyResearchReview(
                            instrument_id=candidate.instrument_id,
                            status="reviewed",
                            classification=classification,
                        )
                    )
                except (RuntimeError, ValueError) as exc:
                    await asyncio.to_thread(
                        repository.append_event,
                        _research_event(
                            strategy_id=strategy_id,
                            instrument_id=candidate.instrument_id,
                            universe_id=universe.universe_id,
                            observed_at=observed_at,
                            state="research_error",
                            reason_code="LLM_SHADOW_REVIEW_ERROR",
                            payload={"detail": str(exc)},
                        ),
                    )
                    reviews.append(
                        StrategyResearchReview(
                            instrument_id=candidate.instrument_id,
                            status="error",
                            detail=str(exc),
                        )
                    )
            return StrategyResearchReviewResponse(
                strategy_id=strategy_id,
                universe_id=universe.universe_id,
                reviews=reviews,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/{strategy_id}/events", response_model=StrategyEventListResponse)
    async def recent_events(strategy_id: str, limit: int = Query(default=200, ge=1, le=1000)):
        try:
            await asyncio.to_thread(repository_factory().get_config, strategy_id)
            events = await asyncio.to_thread(repository_factory().recent_events, strategy_id, limit)
            return StrategyEventListResponse(events=events)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/{strategy_id}/protections", response_model=StrategyProtectionListResponse)
    async def protections(strategy_id: str, active_only: bool = Query(default=True)):
        try:
            await asyncio.to_thread(repository_factory().get_config, strategy_id)
            values = await asyncio.to_thread(repository_factory().list_protections, strategy_id, active_only=active_only)
            return StrategyProtectionListResponse(protections=values)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return router
