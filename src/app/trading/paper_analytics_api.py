from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .paper_analytics import PaperAnalyticsOverview, PaperSimulationEpoch, TradingPaperAnalytics


class PaperEpochListResponse(BaseModel):
    epochs: list[PaperSimulationEpoch]


AnalyticsFactory = Callable[[], TradingPaperAnalytics]


def default_paper_analytics() -> TradingPaperAnalytics:
    return TradingPaperAnalytics()


def create_trading_paper_analytics_router(
    analytics_factory: AnalyticsFactory = default_paper_analytics,
) -> APIRouter:
    router = APIRouter(prefix="/api/trading/paper-analytics", tags=["trading-paper-analytics"])

    @router.get("/epochs", response_model=PaperEpochListResponse)
    async def list_epochs(account_id: str = Query(min_length=1)) -> PaperEpochListResponse:
        try:
            epochs = await asyncio.to_thread(analytics_factory().list_epochs, account_id)
            return PaperEpochListResponse(epochs=epochs)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/overview", response_model=PaperAnalyticsOverview)
    async def overview(
        account_id: str = Query(min_length=1),
        strategy_id: str | None = Query(default=None),
        epoch_id: str | None = Query(default=None),
        mode: Literal["all", "shadow", "auto_paper"] = Query(default="shadow"),
        start_date: date | None = Query(default=None),
        end_date: date | None = Query(default=None),
        rolling_window: int = Query(default=20, ge=5, le=200),
    ) -> PaperAnalyticsOverview:
        if start_date and end_date and end_date < start_date:
            raise HTTPException(status_code=422, detail="analytics_end_date_precedes_start_date")
        try:
            return await asyncio.to_thread(
                analytics_factory().overview,
                account_id,
                strategy_id=strategy_id,
                epoch_id=epoch_id,
                mode=mode,
                start_date=start_date,
                end_date=end_date,
                rolling_window=rolling_window,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return router


__all__ = ["PaperEpochListResponse", "create_trading_paper_analytics_router"]
