from __future__ import annotations

import asyncio
from collections.abc import Callable
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
from .paper_lifecycle import TradingPaperLifecycle, default_paper_lifecycle
from .paper_protection import PaperPositionProtection, PaperProtectionUpsert
from .paper_protection_repository import (
    TradingPaperProtectionRepository,
    default_paper_protection_repository,
)
from .paper_repository import TradingPaperRepository
from .paper_runtime_repository import default_runtime_paper_repository


class PaperAccountListResponse(BaseModel):
    accounts: list[PaperAccount]


class PaperFillListResponse(BaseModel):
    fills: list[PaperFill]


class PaperProtectionListResponse(BaseModel):
    protections: list[PaperPositionProtection]


class PaperResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    initial_cash: Decimal = Field(default=Decimal("100000"), ge=0)


RepositoryFactory = Callable[[], TradingPaperRepository]
LifecycleFactory = Callable[[], TradingPaperLifecycle]
ProtectionRepositoryFactory = Callable[[], TradingPaperProtectionRepository]


def create_trading_paper_router(
    repository_factory: RepositoryFactory = default_runtime_paper_repository,
    lifecycle_factory: LifecycleFactory = default_paper_lifecycle,
    protection_repository_factory: ProtectionRepositoryFactory = default_paper_protection_repository,
) -> APIRouter:
    router = APIRouter(prefix="/api/trading/paper", tags=["trading-paper"])

    @router.get("/accounts", response_model=PaperAccountListResponse)
    async def list_accounts(limit: int = Query(default=100, ge=1, le=500)):
        return PaperAccountListResponse(
            accounts=await asyncio.to_thread(repository_factory().list_accounts, limit)
        )

    @router.post("/accounts", response_model=PaperAccountSnapshot, status_code=201)
    async def create_account(request: PaperAccountCreate):
        try:
            return await asyncio.to_thread(repository_factory().create_account, request)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/accounts/{account_id}", response_model=PaperAccountSnapshot)
    async def account_snapshot(account_id: str):
        try:
            return await asyncio.to_thread(repository_factory().snapshot, account_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get(
        "/accounts/{account_id}/protections",
        response_model=PaperProtectionListResponse,
    )
    async def list_protections(
        account_id: str,
        active_only: bool = Query(default=True),
    ):
        try:
            values = await asyncio.to_thread(
                protection_repository_factory().list,
                account_id,
                active_only=active_only,
            )
            return PaperProtectionListResponse(protections=values)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get(
        "/accounts/{account_id}/protections/{instrument_id:path}",
        response_model=PaperPositionProtection,
    )
    async def get_protection(account_id: str, instrument_id: str):
        try:
            return await asyncio.to_thread(
                protection_repository_factory().get,
                account_id,
                instrument_id,
                include_inactive=False,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.put(
        "/accounts/{account_id}/protections",
        response_model=PaperPositionProtection,
    )
    async def upsert_protection(account_id: str, request: PaperProtectionUpsert):
        try:
            return await asyncio.to_thread(
                protection_repository_factory().upsert,
                account_id,
                request,
            )
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "not_found" in detail else 409 if "already_submitted" in detail else 422
            raise HTTPException(status_code=status, detail=detail) from exc

    @router.delete(
        "/accounts/{account_id}/protections/{instrument_id:path}",
        response_model=PaperPositionProtection,
    )
    async def clear_protection(account_id: str, instrument_id: str):
        try:
            return await asyncio.to_thread(
                protection_repository_factory().clear,
                account_id,
                instrument_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post(
        "/accounts/{account_id}/orders",
        response_model=PaperOrder,
        status_code=201,
    )
    async def place_order(account_id: str, request: PaperOrderRequest):
        """Accept an order without manufacturing a fill from caller price data.

        reference_price is reservation-only. A market order remains open until
        the server-side monitor receives an execution-eligible market observation.
        """
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
        include_in_schema=False,
    )
    async def cancel_order(account_id: str, order_id: str):
        del account_id, order_id
        raise HTTPException(status_code=409, detail="paper_order_cancellation_disabled")

    @router.post(
        "/accounts/{account_id}/observations",
        response_model=PaperFillListResponse,
        include_in_schema=False,
    )
    async def process_observation(
        account_id: str,
        observation: PaperMarketObservation,
    ):
        """Legacy compatibility endpoint; browser-supplied observations never fill.

        Execution observations are server authority and are injected only by the
        paper monitor. Keeping this endpoint as a no-op avoids breaking old web
        clients while removing the previous caller-price execution surface.
        """
        del account_id, observation
        return PaperFillListResponse(fills=[])

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
