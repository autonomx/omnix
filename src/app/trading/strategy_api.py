from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.persistence.errors import RevisionConflict

from .catalyst_repository import TradingCatalystRepository, default_catalyst_repository
from .gapper_dataset import (
    GapperCandidate,
    GapperUniverseSnapshot,
    freeze_gapper_universe,
)
from .gapper_discovery import discover_yahoo_gappers
from .models import MarketBar
from .paper import PaperExecutionPolicy
from .strategies.gap_pullback import evaluate_gap_pullback
from .strategies.models import GapPullbackConfig, GapPullbackResult
from .strategy_backtest import (
    GapPullbackBacktestResult,
    freeze_backtest_session,
    run_gap_pullback_backtest,
)
from .strategy_repository import (
    StrategyEvent,
    StrategyProtection,
    TradingStrategyConfigDocument,
    TradingStrategyRepository,
    default_strategy_repository,
)


class StrategyConfigListResponse(BaseModel):
    strategies: list[TradingStrategyConfigDocument]


class StrategyEventListResponse(BaseModel):
    events: list[StrategyEvent]


class StrategyProtectionListResponse(BaseModel):
    protections: list[StrategyProtection]


class StrategyEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate: dict[str, object]
    bars: list[MarketBar] = Field(default_factory=list, max_length=1000)
    config: GapPullbackConfig = Field(default_factory=GapPullbackConfig)


class GapperUniverseFreezeRequest(BaseModel):
    """Raw point-in-time candidate list; fingerprint is computed by the server."""

    model_config = ConfigDict(extra="forbid")

    universe_id: str = Field(min_length=1, max_length=200)
    session_date: date
    evaluation_time: datetime
    discovery_source: Literal["manual", "import", "scanner", "provider"] = "import"
    candidates: list[GapperCandidate] = Field(min_length=1, max_length=2_000)


class YahooGapperDiscoveryRequest(BaseModel):
    """Current-only Yahoo discovery request; historical reconstruction is forbidden."""

    model_config = ConfigDict(extra="forbid")

    universe_id: str = Field(min_length=1, max_length=200)
    evaluation_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    count: int = Field(default=30, ge=1, le=100)
    minimum_gap_pct: Decimal = Field(default=Decimal("20"), ge=0, le=1000)
    minimum_price: Decimal = Field(default=Decimal("0.50"), gt=0)
    maximum_price: Decimal = Field(default=Decimal("20"), gt=0)


class GapPullbackBacktestRequest(BaseModel):
    """Frozen multi-symbol morning backtest request.

    Candidate membership is supplied by an immutable point-in-time universe;
    there is no hindsight symbol discovery inside the backtester.
    """

    model_config = ConfigDict(extra="forbid")

    session_date: date
    universe: GapperUniverseSnapshot
    bars_by_instrument: dict[str, list[MarketBar]]
    config: GapPullbackConfig = Field(default_factory=GapPullbackConfig)
    execution_policy: PaperExecutionPolicy = Field(
        default_factory=lambda: PaperExecutionPolicy(max_volume_participation_pct=Decimal("1"))
    )
    assumed_spread_bps: Decimal = Field(default=Decimal("40"), ge=0, le=10_000)
    max_hold_minutes: int = Field(default=90, ge=1, le=390)
    max_concurrent_positions: int = Field(default=3, ge=1, le=50)


RepositoryFactory = Callable[[], TradingStrategyRepository]
CatalystRepositoryFactory = Callable[[], TradingCatalystRepository]


def _validate_catalyst_provenance(
    snapshot: GapperUniverseSnapshot,
    catalyst_repository: TradingCatalystRepository,
) -> None:
    evaluation = snapshot.evaluation_time.astimezone(timezone.utc)
    for candidate in snapshot.candidates:
        if not candidate.catalyst_evidence_ids:
            continue
        evidence = catalyst_repository.evidence_by_ids(
            candidate.instrument_id,
            candidate.catalyst_evidence_ids,
        )
        for item in evidence:
            if item.published_at > evaluation or item.captured_at > evaluation:
                raise ValueError(
                    "catalyst_evidence_after_universe_freeze:"
                    f"{candidate.instrument_id}:{item.evidence_id}"
                )


def create_trading_strategy_router(
    repository_factory: RepositoryFactory = default_strategy_repository,
    catalyst_repository_factory: CatalystRepositoryFactory = default_catalyst_repository,
) -> APIRouter:
    router = APIRouter(prefix="/api/trading/strategies", tags=["trading-strategies"])

    @router.get("", response_model=StrategyConfigListResponse)
    async def list_strategies(active_only: bool = Query(default=False)):
        return StrategyConfigListResponse(
            strategies=await asyncio.to_thread(
                repository_factory().list_configs,
                active_only=active_only,
            )
        )

    @router.post("", response_model=TradingStrategyConfigDocument, status_code=201)
    async def create_strategy(document: TradingStrategyConfigDocument):
        try:
            return await asyncio.to_thread(repository_factory().create_config, document)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/backtest/gap-pullback",
        response_model=GapPullbackBacktestResult,
    )
    async def backtest_gap_pullback(request: GapPullbackBacktestRequest):
        """Run deterministic portfolio backtest using the paper fill engine."""
        try:
            _validate_catalyst_provenance(request.universe, catalyst_repository_factory())
            dataset = await asyncio.to_thread(
                freeze_backtest_session,
                session_date=request.session_date,
                universe=request.universe,
                bars_by_instrument=request.bars_by_instrument,
            )
            return await asyncio.to_thread(
                run_gap_pullback_backtest,
                dataset,
                request.config,
                request.execution_policy,
                assumed_spread_bps=request.assumed_spread_bps,
                max_hold_minutes=request.max_hold_minutes,
                max_concurrent_positions=request.max_concurrent_positions,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/universes/discover-yahoo",
        response_model=GapperUniverseSnapshot,
        status_code=201,
    )
    async def discover_yahoo_universe(request: YahooGapperDiscoveryRequest):
        """Discover current Yahoo gainers and freeze the exact point-in-time universe."""
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

    @router.post(
        "/universes/freeze",
        response_model=GapperUniverseSnapshot,
        status_code=201,
    )
    async def freeze_universe(request: GapperUniverseFreezeRequest):
        try:
            snapshot = await asyncio.to_thread(
                freeze_gapper_universe,
                universe_id=request.universe_id,
                session_date=request.session_date,
                evaluation_time=request.evaluation_time,
                discovery_source=request.discovery_source,
                candidates=request.candidates,
            )
            _validate_catalyst_provenance(snapshot, catalyst_repository_factory())
            return await asyncio.to_thread(repository_factory().save_universe, snapshot)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/universes",
        response_model=GapperUniverseSnapshot,
        status_code=201,
    )
    async def save_universe(snapshot: GapperUniverseSnapshot):
        try:
            # Recompute point-in-time validation from the supplied immutable data;
            # do not trust a caller-provided fingerprint alone.
            validated = await asyncio.to_thread(
                freeze_gapper_universe,
                universe_id=snapshot.universe_id,
                session_date=snapshot.session_date,
                evaluation_time=snapshot.evaluation_time,
                discovery_source=snapshot.discovery_source,
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

    @router.post(
        "/evaluate/gap-pullback",
        response_model=GapPullbackResult,
        include_in_schema=True,
    )
    async def evaluate_strategy(request: StrategyEvaluationRequest):
        """Pure read-only evaluation; never persists or places an order."""
        try:
            candidate = GapperCandidate.model_validate(request.candidate)
            return await asyncio.to_thread(
                evaluate_gap_pullback,
                candidate,
                request.bars,
                request.config,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/{strategy_id}", response_model=TradingStrategyConfigDocument)
    async def get_strategy(strategy_id: str):
        try:
            return await asyncio.to_thread(repository_factory().get_config, strategy_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.put("/{strategy_id}", response_model=TradingStrategyConfigDocument)
    async def update_strategy(
        strategy_id: str,
        document: TradingStrategyConfigDocument,
        if_match: int = Header(alias="If-Match", ge=1),
    ):
        try:
            return await asyncio.to_thread(
                repository_factory().update_config,
                strategy_id,
                document,
                expected_revision=if_match,
            )
        except RevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/{strategy_id}/events", response_model=StrategyEventListResponse)
    async def recent_events(
        strategy_id: str,
        limit: int = Query(default=200, ge=1, le=1000),
    ):
        try:
            await asyncio.to_thread(repository_factory().get_config, strategy_id)
            events = await asyncio.to_thread(
                repository_factory().recent_events,
                strategy_id,
                limit,
            )
            return StrategyEventListResponse(events=events)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get(
        "/{strategy_id}/protections",
        response_model=StrategyProtectionListResponse,
    )
    async def protections(
        strategy_id: str,
        active_only: bool = Query(default=True),
    ):
        try:
            await asyncio.to_thread(repository_factory().get_config, strategy_id)
            values = await asyncio.to_thread(
                repository_factory().list_protections,
                strategy_id,
                active_only=active_only,
            )
            return StrategyProtectionListResponse(protections=values)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return router
