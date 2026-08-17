from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.persistence.errors import RevisionConflict

from .paper import (
    PaperAccount,
    PaperAccountCreate,
    PaperAccountSnapshot,
    PaperFill,
    PaperMarketObservation,
    PaperOrder,
    PaperOrderRequest,
)
from .paper_lifecycle import (
    TradingPaperLifecycle,
    default_paper_lifecycle,
)
from .paper_repository import TradingPaperRepository
from .paper_runtime_repository import default_runtime_paper_repository


class PaperAccountListResponse(BaseModel):
    accounts: list[PaperAccount]


class PaperFillListResponse(BaseModel):
    fills: list[PaperFill]


class PaperResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    initial_cash: Decimal = Field(default=Decimal("100000"), ge=0)


RepositoryFactory = Callable[[], TradingPaperRepository]
LifecycleFactory = Callable[[], TradingPaperLifecycle]


def create_trading_paper_router(
    repository_factory: RepositoryFactory = default_runtime_paper_repository,
    lifecycle_factory: LifecycleFactory = default_paper_lifecycle,
) -> APIRouter:
    router = APIRouter(prefix="/api/trading/paper", tags=["trading-paper"])

    @router.get("/accounts", response_model=PaperAccountListResponse)
    async def list_accounts(limit: int = Query(default=100, ge=1, le=500)):
        return PaperAccountListResponse(
            accounts=await asyncio.to_thread(
                repository_factory().list_accounts,
                limit,
            )
        )

    @router.post("/accounts", response_model=PaperAccountSnapshot, status_code=201)
    async def create_account(request: PaperAccountCreate):
        try:
            return await asyncio.to_thread(
                repository_factory().create_account,
                request,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/accounts/{account_id}", response_model=PaperAccountSnapshot)
    async def account_snapshot(account_id: str):
        try:
            return await asyncio.to_thread(
                repository_factory().snapshot,
                account_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post(
        "/accounts/{account_id}/orders",
        response_model=PaperOrder,
        status_code=201,
    )
    async def place_order(account_id: str, request: PaperOrderRequest):
        try:
            repository = repository_factory()
            order = await asyncio.to_thread(
                repository.place_order,
                account_id,
                request,
            )
            if order.order_type == "market" and request.reference_price is not None:
                now = datetime.now(timezone.utc)
                await asyncio.to_thread(
                    repository.process_observation,
                    account_id,
                    PaperMarketObservation(
                        instrument_id=request.instrument_id,
                        binding_id=request.binding_id,
                        provider="paper-reference",
                        price=request.reference_price,
                        source_time=now,
                        evaluated_at=now,
                    ),
                )
                snapshot = await asyncio.to_thread(repository.snapshot, account_id)
                order = next(
                    (
                        candidate
                        for candidate in [*snapshot.order_history, *snapshot.open_orders]
                        if candidate.order_id == request.order_id
                    ),
                    order,
                )
            return order
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "not_found" in detail else 422
            raise HTTPException(status_code=status, detail=detail) from exc

    @router.delete(
        "/accounts/{account_id}/orders/{order_id}",
        response_model=PaperOrder,
        include_in_schema=False,
    )
    async def cancel_order(account_id: str, order_id: str):
        del account_id, order_id
        raise HTTPException(
            status_code=409,
            detail="paper_order_cancellation_disabled",
        )

    @router.post(
        "/accounts/{account_id}/observations",
        response_model=PaperFillListResponse,
    )
    async def process_observation(
        account_id: str,
        observation: PaperMarketObservation,
    ):
        try:
            return PaperFillListResponse(
                fills=await asyncio.to_thread(
                    repository_factory().process_observation,
                    account_id,
                    observation,
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post(
        "/accounts/{account_id}/reset",
        response_model=PaperAccountSnapshot,
    )
    async def reset_account(
        account_id: str,
        request: PaperResetRequest,
        if_match: int = Header(alias="If-Match", ge=1),
    ):
        try:
            return await asyncio.to_thread(
                lifecycle_factory().reset_account,
                account_id,
                initial_cash=request.initial_cash,
                expected_revision=if_match,
            )
        except RevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "not_found" in detail else 422
            raise HTTPException(status_code=status, detail=detail) from exc

    @router.delete(
        "/accounts/{account_id}",
        response_model=PaperAccountSnapshot,
    )
    async def archive_account(
        account_id: str,
        if_match: int = Header(alias="If-Match", ge=1),
    ):
        try:
            return await asyncio.to_thread(
                lifecycle_factory().archive_account,
                account_id,
                expected_revision=if_match,
            )
        except RevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router
