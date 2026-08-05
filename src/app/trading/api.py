from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.persistence.errors import RevisionConflict

from .catalog import BINANCE_POLICY, BINDINGS, search_instruments
from .models import CanonicalInstrument, ProviderBinding, ProviderPolicy
from .repositories import TradingDocumentRepository, default_trading_repository


class ProviderDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    display_name: str
    enabled: bool
    status: Literal["ready", "degraded", "unavailable"]
    policy: ProviderPolicy
    bindings: list[ProviderBinding]


class ProviderStatusResponse(BaseModel):
    ok: bool = True
    providers: list[ProviderDescriptor]


class InstrumentSearchResponse(BaseModel):
    instruments: list[CanonicalInstrument]


class TradingDocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(min_length=1, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)


class TradingDocumentResponse(BaseModel):
    record_id: str
    record_type: str
    revision: int
    payload: dict[str, Any]
    status: str = "active"
    updated_at: str | None = None


class TradingDocumentListResponse(BaseModel):
    records: list[TradingDocumentResponse]


def _document_response(record: dict[str, Any]) -> TradingDocumentResponse:
    return TradingDocumentResponse(
        record_id=str(record["record_id"]),
        record_type=str(record["record_type"]),
        revision=int(record["revision"]),
        payload=dict(record["payload"]),
        status=str(record.get("status") or "active"),
        updated_at=str(record["updated_at"]) if record.get("updated_at") else None,
    )


def create_trading_router(
    repository_factory: Callable[[], TradingDocumentRepository] = default_trading_repository,
) -> APIRouter:
    router = APIRouter(prefix="/api/trading", tags=["trading"])

    @router.get("/providers", response_model=ProviderStatusResponse)
    async def providers() -> ProviderStatusResponse:
        return ProviderStatusResponse(
            providers=[
                ProviderDescriptor(
                    provider="binance",
                    display_name="Binance Public Market Data",
                    enabled=True,
                    status="ready",
                    policy=BINANCE_POLICY,
                    bindings=list(BINDINGS),
                )
            ]
        )

    @router.get("/providers/status", response_model=ProviderStatusResponse)
    async def provider_status() -> ProviderStatusResponse:
        return await providers()

    @router.get("/instruments/search", response_model=InstrumentSearchResponse)
    async def instruments(query: str = Query(default="", max_length=96)) -> InstrumentSearchResponse:
        return InstrumentSearchResponse(instruments=search_instruments(query))

    def register_documents(path: str, record_type: str) -> None:
        @router.get(path, response_model=TradingDocumentListResponse, name=f"list_trading_{record_type}s")
        async def list_documents(limit: int = Query(default=100, ge=1, le=500)) -> TradingDocumentListResponse:
            records = repository_factory().list(record_type, limit=limit)
            return TradingDocumentListResponse(records=[_document_response(record) for record in records])

        @router.post(path, response_model=TradingDocumentResponse, status_code=201, name=f"create_trading_{record_type}")
        async def create_document(request: TradingDocumentRequest) -> TradingDocumentResponse:
            try:
                record = repository_factory().create(record_type, request.record_id, request.payload)
            except RevisionConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return _document_response(record)

        @router.get(f"{path}/{{record_id}}", response_model=TradingDocumentResponse, name=f"get_trading_{record_type}")
        async def get_document(record_id: str) -> TradingDocumentResponse:
            record = repository_factory().get(record_type, record_id)
            if record is None:
                raise HTTPException(status_code=404, detail=f"{record_type}_not_found")
            return _document_response(record)

        @router.put(f"{path}/{{record_id}}", response_model=TradingDocumentResponse, name=f"update_trading_{record_type}")
        async def update_document(
            record_id: str,
            request: TradingDocumentRequest,
            if_match: int = Header(alias="If-Match", ge=1),
        ) -> TradingDocumentResponse:
            if request.record_id != record_id:
                raise HTTPException(status_code=422, detail="record_id_mismatch")
            try:
                record = repository_factory().update(
                    record_type,
                    record_id,
                    request.payload,
                    expected_revision=if_match,
                )
            except RevisionConflict as exc:
                current = repository_factory().get(record_type, record_id)
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "revision_conflict",
                        "message": str(exc),
                        "current_revision": current.get("revision") if current else None,
                    },
                ) from exc
            return _document_response(record)

    register_documents("/workspaces", "workspace")
    register_documents("/watchlists", "watchlist")
    register_documents("/drawings", "drawing")
    register_documents("/indicator-presets", "indicator_preset")
    return router
