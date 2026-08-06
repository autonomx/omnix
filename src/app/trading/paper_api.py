from __future__ import annotations

import asyncio
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .paper import (
    PaperAccount,
    PaperAccountCreate,
    PaperAccountSnapshot,
    PaperFill,
    PaperMarketObservation,
    PaperOrder,
    PaperOrderRequest,
)
from .paper_repository import TradingPaperRepository, default_paper_repository


class PaperAccountListResponse(BaseModel):
    accounts: list[PaperAccount]


class PaperFillListResponse(BaseModel):
    fills: list[PaperFill]


RepositoryFactory = Callable[[], TradingPaperRepository]


def create_trading_paper_router(
    repository_factory: RepositoryFactory = default_paper_repository,
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
            return await asyncio.to_thread(
                repository_factory().place_order,
                account_id,
                request,
            )
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "not_found" in detail else 422
            raise HTTPException(status_code=status, detail=detail) from exc

    @router.delete(
        "/accounts/{account_id}/orders/{order_id}",
        response_model=PaperOrder,
    )
    async def cancel_order(account_id: str, order_id: str):
        try:
            return await asyncio.to_thread(
                repository_factory().cancel_order,
                account_id,
                order_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

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

    return router
