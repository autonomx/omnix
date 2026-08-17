from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .backtest import BacktestRequest, BacktestRunResult, run_backtest
from .replay import FrozenDatasetSnapshot, freeze_bars_response
from .replay_repository import TradingReplayRepository
from .replay_runtime_repository import default_runtime_replay_repository
from .service import TradingMarketDataService, default_market_data_service


class FreezeDatasetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1, max_length=200)
    instrument_id: str = Field(min_length=3, max_length=200)
    binding_id: str | None = Field(default=None, max_length=240)
    interval: str = Field(default="1d", min_length=1, max_length=16)
    limit: int = Field(default=500, ge=1, le=5_000)
    gap_policy: Literal["fail", "skip"] = "fail"


class DatasetListResponse(BaseModel):
    datasets: list[FrozenDatasetSnapshot]


class BacktestRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    request: BacktestRequest = Field(default_factory=BacktestRequest)


class BacktestListResponse(BaseModel):
    runs: list[dict[str, object]]


RepositoryFactory = Callable[[], TradingReplayRepository]
MarketServiceFactory = Callable[[], TradingMarketDataService]


def create_trading_replay_router(
    repository_factory: RepositoryFactory = default_runtime_replay_repository,
    market_service_factory: MarketServiceFactory = default_market_data_service,
) -> APIRouter:
    router = APIRouter(prefix="/api/trading/replay", tags=["trading-replay"])

    @router.post("/datasets", response_model=FrozenDatasetSnapshot, status_code=201)
    async def freeze_dataset(request: FreezeDatasetRequest):
        try:
            service = market_service_factory()
            response = await asyncio.to_thread(
                service.bars,
                request.instrument_id,
                request.interval,
                request.limit,
                request.binding_id,
            )
            snapshot = freeze_bars_response(
                dataset_id=request.dataset_id,
                response=response,
                requested_binding_id=request.binding_id,
                gap_policy=request.gap_policy,
            )
            return await asyncio.to_thread(
                repository_factory().create_dataset,
                snapshot,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/datasets", response_model=DatasetListResponse)
    async def list_datasets(limit: int = Query(default=100, ge=1, le=500)):
        return DatasetListResponse(
            datasets=await asyncio.to_thread(
                repository_factory().list_datasets,
                limit,
            )
        )

    @router.get("/datasets/{dataset_id}", response_model=FrozenDatasetSnapshot)
    async def get_dataset(dataset_id: str):
        snapshot = await asyncio.to_thread(
            repository_factory().get_dataset,
            dataset_id,
        )
        if snapshot is None:
            raise HTTPException(status_code=404, detail="dataset_not_found")
        return snapshot

    @router.post("/backtests", response_model=BacktestRunResult, status_code=201)
    async def create_backtest(request: BacktestRunRequest):
        repository = repository_factory()
        snapshot = await asyncio.to_thread(
            repository.get_dataset,
            request.dataset_id,
        )
        if snapshot is None:
            raise HTTPException(status_code=404, detail="dataset_not_found")
        result = await asyncio.to_thread(
            run_backtest,
            snapshot,
            request.request,
            run_id=f"backtest-{uuid4().hex}",
        )
        return await asyncio.to_thread(repository.save_backtest, result)

    @router.get("/backtests", response_model=BacktestListResponse)
    async def list_backtests(limit: int = Query(default=100, ge=1, le=500)):
        return BacktestListResponse(
            runs=await asyncio.to_thread(
                repository_factory().list_backtests,
                limit,
            )
        )

    @router.get("/backtests/{run_id}", response_model=BacktestRunResult)
    async def get_backtest(run_id: str):
        result = await asyncio.to_thread(
            repository_factory().get_backtest,
            run_id,
        )
        if result is None:
            raise HTTPException(status_code=404, detail="backtest_not_found")
        return result

    return router
