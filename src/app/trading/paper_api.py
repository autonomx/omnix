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
from .paper_risk import (
    PaperRiskOrderRequest,
    PaperRiskPreview,
    PaperRiskPreviewRequest,
    preview_paper_risk,
    risk_order_request,
    risk_protection_request,
)
from .paper_runtime_repository import default_runtime_paper_repository
from .service import TradingMarketDataService, default_market_data_service


class PaperAccountListResponse(BaseModel):
    accounts: list[PaperAccount]


class PaperFillListResponse(BaseModel):
    fills: list[PaperFill]


class PaperProtectionListResponse(BaseModel):
    protections: list[PaperPositionProtection]


class PaperResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    initial_cash: Decimal = Field(default=Decimal("100000"), ge=0)


class PaperOrderReplaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    replacement: PaperOrderRequest


class PaperOrderReplaceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cancelled: PaperOrder
    replacement: PaperOrder


class PaperRiskOrderResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview: PaperRiskPreview
    order: PaperOrder
    protection: PaperPositionProtection


RepositoryFactory = Callable[[], TradingPaperRepository]
LifecycleFactory = Callable[[], TradingPaperLifecycle]
ProtectionRepositoryFactory = Callable[[], TradingPaperProtectionRepository]
MarketServiceFactory = Callable[[], TradingMarketDataService]
_ORDER_MANAGEMENT_HEADER = "X-Omnix-Paper-Order-Management"
_ORDER_MANAGEMENT_VERSION = "v2"


def _require_order_management(version: str | None) -> None:
    # Preserve the legacy disabled route for old clients while allowing the new
    # workstation to opt into explicit cancel/replace semantics.
    if version != _ORDER_MANAGEMENT_VERSION:
        raise HTTPException(status_code=409, detail="paper_order_cancellation_disabled")


def create_trading_paper_router(
    repository_factory: RepositoryFactory = default_runtime_paper_repository,
    lifecycle_factory: LifecycleFactory = default_paper_lifecycle,
    protection_repository_factory: ProtectionRepositoryFactory = default_paper_protection_repository,
    market_service_factory: MarketServiceFactory = default_market_data_service,
) -> APIRouter:
    router = APIRouter(prefix="/api/trading/paper", tags=["trading-paper"])

    async def risk_context(account_id: str, request: PaperRiskPreviewRequest):
        repository = repository_factory()
        protections = protection_repository_factory()
        try:
            snapshot, active_protections, execution = await asyncio.gather(
                asyncio.to_thread(repository.snapshot, account_id),
                asyncio.to_thread(protections.list, account_id, active_only=True),
                asyncio.to_thread(
                    market_service_factory().execution_observation,
                    request.instrument_id,
                    request.binding_id,
                ),
            )
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "account_not_found" in detail else 422
            raise HTTPException(status_code=status, detail=detail) from exc
        return snapshot, active_protections, execution

    async def evaluate_risk(account_id: str, request: PaperRiskPreviewRequest) -> PaperRiskPreview:
        snapshot, active_protections, execution = await risk_context(account_id, request)
        return preview_paper_risk(
            snapshot=snapshot,
            protections=active_protections,
            observation=execution,
            request=request,
        )

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

    @router.post(
        "/accounts/{account_id}/risk-preview",
        response_model=PaperRiskPreview,
        include_in_schema=False,
    )
    async def risk_preview(account_id: str, request: PaperRiskPreviewRequest):
        """Return the canonical server sizing/risk decision for a proposed long entry."""
        return await evaluate_risk(account_id, request)

    @router.post(
        "/accounts/{account_id}/risk-orders",
        response_model=PaperRiskOrderResult,
        include_in_schema=False,
        status_code=201,
    )
    async def place_risk_order(account_id: str, request: PaperRiskOrderRequest):
        """Size and submit a new long entry entirely from server-owned risk rules."""
        probe_price = request.trigger_price or Decimal("1")
        probe = PaperRiskPreviewRequest(
            instrument_id=request.instrument_id,
            binding_id=request.binding_id,
            entry_price=probe_price,
            stop_price=request.stop_loss,
            desired_risk_pct=request.desired_risk_pct,
        )
        snapshot, active_protections, execution = await risk_context(account_id, probe)
        entry_price = (
            (execution.ask or execution.last)
            if request.order_type == "market"
            else request.trigger_price
        )
        if entry_price is None:
            raise HTTPException(status_code=422, detail="paper_risk_entry_price_unavailable")
        preview_request = PaperRiskPreviewRequest(
            instrument_id=request.instrument_id,
            binding_id=request.binding_id,
            entry_price=entry_price,
            stop_price=request.stop_loss,
            desired_risk_pct=request.desired_risk_pct,
        )
        preview = preview_paper_risk(
            snapshot=snapshot,
            protections=active_protections,
            observation=execution,
            request=preview_request,
        )
        if not preview.allowed or preview.recommended_quantity <= 0:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "paper_risk_rejected",
                    "reason_codes": list(preview.reason_codes),
                    "preview": preview.model_dump(mode="json"),
                },
            )

        repository = repository_factory()
        protection_repository = protection_repository_factory()
        order_request = risk_order_request(
            request,
            entry_price=entry_price,
            quantity=preview.recommended_quantity,
        )
        try:
            order = await asyncio.to_thread(repository.place_order, account_id, order_request)
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "not_found" in detail else 409 if "insufficient" in detail else 422
            raise HTTPException(status_code=status, detail=detail) from exc

        try:
            protection = await asyncio.to_thread(
                protection_repository.upsert,
                account_id,
                risk_protection_request(request),
            )
        except ValueError as exc:
            # Normally the order is still open because the monitor is asynchronous.
            # Fail closed by cancelling it if its protection cannot be persisted.
            cancel_error = None
            try:
                await asyncio.to_thread(repository.cancel_order, account_id, order.order_id)
            except ValueError as cancel_exc:
                cancel_error = str(cancel_exc)
            detail = f"paper_risk_protection_failed:{exc}"
            if cancel_error:
                detail += f":cancel_failed:{cancel_error}"
            raise HTTPException(status_code=409, detail=detail) from exc

        return PaperRiskOrderResult(preview=preview, order=order, protection=protection)

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
    async def cancel_order(
        account_id: str,
        order_id: str,
        order_management: str | None = Header(default=None, alias=_ORDER_MANAGEMENT_HEADER),
    ):
        _require_order_management(order_management)
        try:
            return await asyncio.to_thread(
                repository_factory().cancel_order,
                account_id,
                order_id,
            )
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "account_not_found" in detail else 409 if "not_open" in detail else 422
            raise HTTPException(status_code=status, detail=detail) from exc

    @router.post(
        "/accounts/{account_id}/orders/{order_id}/replace",
        response_model=PaperOrderReplaceResponse,
        include_in_schema=False,
    )
    async def replace_order(
        account_id: str,
        order_id: str,
        request: PaperOrderReplaceRequest,
        order_management: str | None = Header(default=None, alias=_ORDER_MANAGEMENT_HEADER),
    ):
        _require_order_management(order_management)
        repository = repository_factory()
        try:
            cancelled = await asyncio.to_thread(repository.cancel_order, account_id, order_id)
        except ValueError as exc:
            detail = str(exc)
            status = 404 if "account_not_found" in detail else 409 if "not_open" in detail else 422
            raise HTTPException(status_code=status, detail=detail) from exc
        try:
            replacement = await asyncio.to_thread(
                repository.place_order,
                account_id,
                request.replacement,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail=f"paper_order_replacement_failed_after_cancel:{exc}",
            ) from exc
        return PaperOrderReplaceResponse(cancelled=cancelled, replacement=replacement)

    @router.post(
        "/accounts/{account_id}/observations",
        response_model=PaperFillListResponse,
        include_in_schema=False,
    )
    async def process_observation(
        account_id: str,
        observation: PaperMarketObservation,
    ):
        """Legacy compatibility endpoint; browser-supplied observations never fill."""
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