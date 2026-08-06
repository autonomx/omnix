from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from .research import (
    MarketResearchRequest,
    MarketResearchResult,
    ProviderFactory,
    default_research_provider,
    generate_market_research,
)
from .service import TradingMarketDataService, default_market_data_service


MarketServiceFactory = Callable[[], TradingMarketDataService]


def create_trading_research_router(
    market_service_factory: MarketServiceFactory = default_market_data_service,
    provider_factory: ProviderFactory = default_research_provider,
) -> APIRouter:
    router = APIRouter(prefix="/api/trading/research", tags=["trading-research"])

    @router.post("", response_model=MarketResearchResult)
    async def create_research(request: MarketResearchRequest):
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    generate_market_research,
                    request,
                    market_service_factory=market_service_factory,
                    provider_factory=provider_factory,
                ),
                timeout=90,
            )
        except asyncio.TimeoutError as exc:
            raise HTTPException(
                status_code=504,
                detail={"code": "research_timeout", "message": "The registered provider exceeded 90 seconds."},
            ) from exc
        except (json.JSONDecodeError, ValidationError) as exc:
            raise HTTPException(
                status_code=502,
                detail={"code": "invalid_research_output", "message": str(exc)},
            ) from exc
        except ValueError as exc:
            message = str(exc)
            provider_failure = any(
                marker in message
                for marker in (
                    "provider_",
                    "registered_provider",
                    "research_output",
                )
            )
            raise HTTPException(
                status_code=502 if provider_failure else 422,
                detail={
                    "code": "research_provider_failed" if provider_failure else "invalid_research_request",
                    "message": message,
                },
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": "research_provider_unavailable", "message": str(exc)},
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail={"code": "research_failed", "message": f"{type(exc).__name__}: {exc}"},
            ) from exc

    return router
