from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from .execution import ExecutionObservation
from .service import TradingMarketDataService, default_market_data_service


def create_trading_execution_router(
    market_service_factory=default_market_data_service,
) -> APIRouter:
    router = APIRouter(prefix="/api/trading/execution", tags=["trading-execution"])

    @router.get("/observation", response_model=ExecutionObservation)
    async def observation(
        instrument_id: str = Query(min_length=3, max_length=200),
        binding_id: str | None = Query(default=None, max_length=240),
    ) -> ExecutionObservation:
        try:
            service: TradingMarketDataService = market_service_factory()
            return await asyncio.to_thread(
                service.execution_observation,
                instrument_id,
                binding_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail={"code": "execution_market_data_failed", "message": str(exc)},
            ) from exc

    return router
