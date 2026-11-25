from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError

from .research import (
    MarketResearchRequest,
    MarketResearchResult,
    ProviderFactory,
    generate_market_research,
    interactive_research_provider,
)
from .research.chart_copilot import CopilotRequest, CopilotResult, chart_copilot
from .research.filing_summaries import FilingList, FilingSummaries, FilingSummaryRequest, FilingSummaryResult
from .research.news_digest import NewsDigestRequest, NewsDigestResult, news_digest
from .research.range_research import RangeResearchRequest, RangeResearchResult, research_range
from .sec_contact import SecContactRequired
from .service import TradingMarketDataService, default_market_data_service

logger = logging.getLogger(__name__)


MarketServiceFactory = Callable[[], TradingMarketDataService]


def create_trading_research_router(
    market_service_factory: MarketServiceFactory = default_market_data_service,
    # A person is waiting on these answers: the app's default provider, not the Trading model setting.
    provider_factory: ProviderFactory = interactive_research_provider,
    filing_summaries: FilingSummaries | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/trading/research", tags=["trading-research"])
    # One per router: it keeps the summaries it has written.
    filings = filing_summaries or FilingSummaries(provider_factory=provider_factory)

    @router.post("", response_model=MarketResearchResult)
    async def create_research(request: MarketResearchRequest):
        return await _answer(lambda: generate_market_research(
            request, market_service_factory=market_service_factory, provider_factory=provider_factory,
        ))

    @router.post("/range", response_model=RangeResearchResult)
    async def research_chart_range(request: RangeResearchRequest):
        """AI Range: explain, find the events behind or analyze a span selected on the chart, or answer a question about it."""
        return await _answer(lambda: research_range(
            request, market_service_factory=market_service_factory, provider_factory=provider_factory,
        ))

    @router.post("/copilot", response_model=CopilotResult)
    async def chart_copilot_turn(request: CopilotRequest):
        """Chart Copilot: answer a question about the chart and propose chart changes the person may apply."""
        return await _answer(lambda: chart_copilot(
            request, market_service_factory=market_service_factory, provider_factory=provider_factory,
        ))

    @router.post("/news-digest", response_model=NewsDigestResult)
    async def summarize_news(request: NewsDigestRequest):
        """AI news digest: the symbol's recent headlines, summarized by theme."""
        return await _answer(lambda: news_digest(request, provider_factory=provider_factory))

    @router.get("/filings", response_model=FilingList)
    async def list_filings(instrument_id: str = Query(min_length=3, max_length=200)):
        """A US company's recent SEC reports, for AI filing summaries."""
        return await _answer(lambda: filings.filings(instrument_id))

    @router.post("/filings/summary", response_model=FilingSummaryResult)
    async def summarize_filing(request: FilingSummaryRequest):
        """AI filing summary: one of the company's recent SEC reports, summarized from its own text."""
        return await _answer(lambda: filings.summary(request))

    return router


async def _answer(run: Callable[[], Any]) -> Any:
    """Run one research call off the event loop, with its failures as the API's error codes."""
    try:
        return await asyncio.wait_for(asyncio.to_thread(run), timeout=90)
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail={"code": "research_timeout", "message": "The registered provider exceeded 90 seconds."},
        ) from exc
    except (json.JSONDecodeError, ValidationError) as exc:
        # The parse error quotes the provider's reply: log it, return the code (WP-10.5).
        logger.warning("invalid_research_output", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail={"code": "invalid_research_output", "message": "The research provider returned an unreadable result."},
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
        if provider_failure:
            logger.warning("research_provider_failed", exc_info=True)
        raise HTTPException(
            status_code=502 if provider_failure else 422,
            detail={
                "code": "research_provider_failed" if provider_failure else "invalid_research_request",
                # A provider's reply stays in the log; validation messages are Omnix's own.
                "message": "The research provider request failed." if provider_failure else message,
            },
        ) from exc
    except SecContactRequired as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)}) from exc
    except RuntimeError as exc:
        logger.warning("research_provider_unavailable", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={"code": "research_provider_unavailable", "message": "The research provider is unavailable."},
        ) from exc
    except Exception as exc:
        logger.warning("research_failed", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail={"code": "research_failed", "message": "The research provider request failed."},
        ) from exc

