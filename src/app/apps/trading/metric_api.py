from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query

from .breadth import BREADTH_METRICS, BreadthRepository, breadth_metric, default_breadth_repository
from .fundamental_metric_data import (
    YahooAnalystMetricAdapter,
    default_yahoo_analyst_metric_adapter,
)
from .metric_data import (
    MarketMetricResponse,
    TradingMetricDataService,
    default_metric_data_service,
)

logger = logging.getLogger(__name__)


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
    yahoo_analyst_factory: Callable[[], YahooAnalystMetricAdapter] = default_yahoo_analyst_metric_adapter,
    breadth_repository_factory: Callable[[], BreadthRepository] = default_breadth_repository,
) -> APIRouter:
    router = APIRouter(prefix="/api/trading", tags=["trading"])

    # This is an internal chart transport, not a stable generated-client API.
    # The indicator scheduler consumes the typed payload directly, so keep it
    # out of the shared public gateway contract until metric subscriptions are
    # promoted to a versioned external API.
    @router.get("/metrics", response_model=MarketMetricResponse)
    def metric_series(
        instrument_id: str = Query(min_length=3, max_length=200),
        metric: str = Query(min_length=3, max_length=120),
        interval: str = Query(default="1h", max_length=16),
        limit: int = Query(default=500, ge=1, le=1_500),
        end_time: datetime | None = Query(default=None),
    ) -> MarketMetricResponse:
        try:
            if metric in BREADTH_METRICS:
                # Market breadth (TVP-6.6): the same for every chart.
                response = breadth_metric(metric, breadth_repository_factory(), instrument_id=instrument_id, interval=interval, limit=limit, end_time=end_time)
            elif metric in {"yahoo.analyst_price_forecast", "yahoo.price_target"}:
                response = yahoo_analyst_factory().analyst_targets(
                    instrument_id,
                    interval,
                    limit,
                    end_time=end_time,
                )
                if metric == "yahoo.price_target":
                    response = response.model_copy(update={"metric": metric})
            else:
                response = metric_service_factory().metric(
                    instrument_id,
                    metric,
                    interval,
                    limit,
                    end_time=end_time,
                )
            return _normalize_metric_units(response)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            # The provider error can carry URLs and credentials: log it, return the code (WP-10.5).
            logger.warning("metric_data_failed", exc_info=True)
            raise HTTPException(
                status_code=502,
                detail={"code": "metric_data_failed", "message": "The metric data request failed."},
            ) from exc

    return router
