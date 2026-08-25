from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from .metric_data import (
    MarketMetricResponse,
    TradingMetricDataService,
    default_metric_data_service,
)


def create_trading_metric_router(
    metric_service_factory: Callable[[], TradingMetricDataService] = default_metric_data_service,
) -> APIRouter:
    router = APIRouter(prefix="/api/trading", tags=["trading"])

    @router.get("/metrics", response_model=MarketMetricResponse)
    async def metric_series(
        instrument_id: str = Query(min_length=3, max_length=200),
        metric: str = Query(min_length=3, max_length=120),
        interval: str = Query(default="1h", max_length=16),
        limit: int = Query(default=500, ge=1, le=1_500),
        end_time: datetime | None = Query(default=None),
    ) -> MarketMetricResponse:
        try:
            return metric_service_factory().metric(
                instrument_id,
                metric,
                interval,
                limit,
                end_time=end_time,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail={"code": "metric_data_failed", "message": str(exc)},
            ) from exc

    return router
