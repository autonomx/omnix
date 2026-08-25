from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query

from .metric_data import (
    MarketMetricResponse,
    TradingMetricDataService,
    default_metric_data_service,
)


def _normalize_metric_units(response: MarketMetricResponse) -> MarketMetricResponse:
    """Normalize provider-native units to the units exposed by the chart metric."""
    if response.metric != "binance.premium":
        return response
    return response.model_copy(
        update={
            "series": [
                series.model_copy(
                    update={
                        "points": [
                            point.model_copy(update={"value": point.value * Decimal("100")})
                            for point in series.points
                        ]
                    }
                )
                for series in response.series
            ]
        }
    )


def create_trading_metric_router(
    metric_service_factory: Callable[[], TradingMetricDataService] = default_metric_data_service,
) -> APIRouter:
    router = APIRouter(prefix="/api/trading", tags=["trading"])

    # This is an internal chart transport, not a stable generated-client API.
    # The indicator scheduler consumes the typed payload directly, so keep it
    # out of the shared public gateway contract until metric subscriptions are
    # promoted to a versioned external API.
    @router.get("/metrics", response_model=MarketMetricResponse, include_in_schema=False)
    async def metric_series(
        instrument_id: str = Query(min_length=3, max_length=200),
        metric: str = Query(min_length=3, max_length=120),
        interval: str = Query(default="1h", max_length=16),
        limit: int = Query(default=500, ge=1, le=1_500),
        end_time: datetime | None = Query(default=None),
    ) -> MarketMetricResponse:
        try:
            return _normalize_metric_units(
                metric_service_factory().metric(
                    instrument_id,
                    metric,
                    interval,
                    limit,
                    end_time=end_time,
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail={"code": "metric_data_failed", "message": str(exc)},
            ) from exc

    return router
