from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field

from app.persistence.errors import RevisionConflict

from .instrument_catalog_service import ProviderBackedInstrumentCatalog, default_instrument_catalog
from .models import BarsResponse, CanonicalInstrument, ProviderBinding, ProviderPolicy
from .repositories import TradingDocumentRepository, default_trading_repository
from .service import TradingMarketDataService, default_market_data_service
from .streaming.manager import StreamingBarUpdate


class ProviderRuntimeStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0
    rate_limit_count: int = 0
    in_flight: int = 0
    max_concurrency: int = 0
    last_success_at: str | None = None
    last_failure_at: str | None = None
    last_error: str | None = None


class ProviderDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    display_name: str
    enabled: bool
    status: Literal["ready", "degraded", "unavailable", "unconfigured"]
    policy: ProviderPolicy
    bindings: list[ProviderBinding]
    runtime: ProviderRuntimeStatus = Field(default_factory=ProviderRuntimeStatus)


class ProviderStatusResponse(BaseModel):
    ok: bool = True
    providers: list[ProviderDescriptor]


class InstrumentSearchResponse(BaseModel):
    instruments: list[CanonicalInstrument]


class QuoteResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    instrument_id: str
    binding_id: str
    provider: str
    price: str
    received_at: str
    freshness_mode: str


class CurrencyRateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_currency: str
    quote_currency: str
    rate: float
    provider: str
    received_at: str
    freshness_mode: str


class TradingDiagnosticsResponse(BaseModel):
    ok: bool = True
    diagnostics: dict[str, Any]


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


def _stream_payload(update: StreamingBarUpdate) -> dict[str, Any]:
    payload = asdict(update)
    for key, value in tuple(payload.items()):
        if isinstance(value, datetime):
            payload[key] = value.isoformat()
        elif isinstance(value, Decimal):
            payload[key] = str(value)
    return {"type": "bar", "bar": payload}


def create_trading_router(
    repository_factory: Callable[[], TradingDocumentRepository] = default_trading_repository,
    market_service_factory: Callable[[], TradingMarketDataService] = default_market_data_service,
    instrument_catalog_factory: Callable[[], ProviderBackedInstrumentCatalog] = default_instrument_catalog,
) -> APIRouter:
    router = APIRouter(prefix="/api/trading", tags=["trading"])

    @router.get("/providers", response_model=ProviderStatusResponse)
    async def providers() -> ProviderStatusResponse:
        descriptors = [
            ProviderDescriptor.model_validate(item)
            for item in market_service_factory().provider_descriptors()
        ]
        return ProviderStatusResponse(providers=descriptors)

    @router.get("/providers/status", response_model=ProviderStatusResponse)
    async def provider_status() -> ProviderStatusResponse:
        return await providers()

    @router.get("/instruments/search", response_model=InstrumentSearchResponse)
    async def instruments(query: str = Query(default="", max_length=96)) -> InstrumentSearchResponse:
        catalog = instrument_catalog_factory()
        results = await asyncio.to_thread(catalog.search, query)
        return InstrumentSearchResponse(instruments=results)

    @router.get("/bars", response_model=BarsResponse)
    async def bars(
        instrument_id: str = Query(min_length=3, max_length=200),
        interval: str = Query(default="1m", max_length=16),
        limit: int = Query(default=500, ge=1, le=5_000),
        binding_id: str | None = Query(default=None, max_length=240),
    ) -> BarsResponse:
        try:
            service = market_service_factory()
            if binding_id is None:
                return service.bars(instrument_id, interval, limit)
            return service.bars(instrument_id, interval, limit, binding_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail={"code": "market_data_failed", "message": str(exc)},
            ) from exc

    @router.get("/quotes", response_model=QuoteResponse)
    async def quote(
        instrument_id: str = Query(min_length=3, max_length=200),
        binding_id: str | None = Query(default=None, max_length=240),
    ) -> QuoteResponse:
        try:
            service = market_service_factory()
            result = (
                service.quote(instrument_id)
                if binding_id is None
                else service.quote(instrument_id, binding_id)
            )
            return QuoteResponse.model_validate(result)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail={"code": "quote_failed", "message": str(exc)},
            ) from exc

    @router.get("/currency-rates", response_model=CurrencyRateResponse)
    async def currency_rate(
        base_currency: str = Query(min_length=3, max_length=16),
        quote_currency: str = Query(min_length=3, max_length=16),
    ) -> CurrencyRateResponse:
        try:
            result = market_service_factory().currency_rate(base_currency, quote_currency)
            return CurrencyRateResponse.model_validate(result)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail={"code": "currency_rate_failed", "message": str(exc)},
            ) from exc

    @router.get("/diagnostics", response_model=TradingDiagnosticsResponse)
    async def diagnostics() -> TradingDiagnosticsResponse:
        return TradingDiagnosticsResponse(
            diagnostics=market_service_factory().diagnostics()
        )

    @router.websocket("/stream")
    async def stream(websocket: WebSocket) -> None:
        instrument_id = websocket.query_params.get("instrument_id", "")
        interval = websocket.query_params.get("interval", "1m")
        binding_id = websocket.query_params.get("binding_id") or None
        if not instrument_id:
            await websocket.close(code=1008, reason="instrument_id is required")
            return
        await websocket.accept()
        try:
            service = market_service_factory()
            updates = (
                service.stream_updates(instrument_id, interval)
                if binding_id is None
                else service.stream_updates(instrument_id, interval, binding_id)
            )
            async for update in updates:
                await websocket.send_json(_stream_payload(update))
        except WebSocketDisconnect:
            return
        except ValueError as exc:
            await websocket.send_json(
                {"type": "error", "code": "invalid_stream", "message": str(exc)}
            )
            await websocket.close(code=1008)
        except Exception as exc:
            await websocket.send_json(
                {"type": "error", "code": "stream_failed", "message": str(exc)}
            )
            await websocket.close(code=1011)

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

        @router.delete(f"{path}/{{record_id}}", response_model=TradingDocumentResponse, name=f"archive_trading_{record_type}")
        async def archive_document(
            record_id: str,
            if_match: int = Header(alias="If-Match", ge=1),
        ) -> TradingDocumentResponse:
            try:
                record = repository_factory().archive(
                    record_type,
                    record_id,
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
