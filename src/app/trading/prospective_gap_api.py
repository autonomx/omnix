from __future__ import annotations

"""API for the machine-readable prospective-gap experiment authority."""

from datetime import date, datetime, timezone
from typing import Callable

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from .prospective_gap_repository import ProspectiveGapSessionLedger
from .prospective_gap_runtime import (
    ConfirmationRunResult,
    PostcloseRunResult,
    PremarketFreezeRequest,
    PremarketFreezeResult,
    ProspectiveGapRuntime,
    default_prospective_gap_runtime,
)


RuntimeFactory = Callable[[], ProspectiveGapRuntime]


class ConfirmationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_date: date
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PostcloseRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_date: date
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MarkdownProjectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_date: date
    markdown: str
    authority: str = "prospective-gap StrategyEvent ledger"


def create_trading_prospective_gap_router(
    runtime_factory: RuntimeFactory = default_prospective_gap_runtime,
) -> APIRouter:
    router = APIRouter(
        prefix="/api/trading/prospective-gap",
        tags=["trading-prospective-gap"],
    )

    @router.post("/premarket/freeze", response_model=PremarketFreezeResult)
    async def freeze_premarket(request: PremarketFreezeRequest) -> PremarketFreezeResult:
        return runtime_factory().freeze_premarket(request)

    @router.post("/confirmation/run", response_model=ConfirmationRunResult)
    async def run_confirmation(request: ConfirmationRunRequest) -> ConfirmationRunResult:
        return runtime_factory().run_confirmation(
            session_date=request.session_date,
            evaluated_at=request.evaluated_at,
        )

    @router.post("/postclose/finalize", response_model=PostcloseRunResult)
    async def finalize_postclose(request: PostcloseRunRequest) -> PostcloseRunResult:
        return runtime_factory().finalize_postclose(
            session_date=request.session_date,
            evaluated_at=request.evaluated_at,
        )

    @router.get("/session/{session_date}", response_model=ProspectiveGapSessionLedger)
    async def session_ledger(session_date: date) -> ProspectiveGapSessionLedger:
        return runtime_factory().session_ledger(session_date)

    @router.get(
        "/session/{session_date}/markdown",
        response_model=MarkdownProjectionResponse,
    )
    async def markdown_projection(session_date: date) -> MarkdownProjectionResponse:
        return MarkdownProjectionResponse(
            session_date=session_date,
            markdown=runtime_factory().render_markdown(session_date),
        )

    return router


__all__ = [
    "ConfirmationRunRequest",
    "MarkdownProjectionResponse",
    "PostcloseRunRequest",
    "create_trading_prospective_gap_router",
]
