from __future__ import annotations

import asyncio
from collections.abc import Callable

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.persistence.errors import RevisionConflict

from .gapper_dataset import GapperUniverseSnapshot
from .models import MarketBar
from .strategies.gap_pullback import evaluate_gap_pullback
from .strategies.models import GapPullbackConfig, GapPullbackResult
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


RepositoryFactory = Callable[[], TradingStrategyRepository]


def create_trading_strategy_router(
    repository_factory: RepositoryFactory = default_strategy_repository,
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

    @router.post(
        "/universes",
        response_model=GapperUniverseSnapshot,
        status_code=201,
    )
    async def save_universe(snapshot: GapperUniverseSnapshot):
        try:
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
        from .gapper_dataset import GapperCandidate

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

    return router
