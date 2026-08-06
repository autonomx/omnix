from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from app.persistence.errors import RevisionConflict

from .alerts import (
    TradingAlert,
    TradingAlertCreate,
    TradingAlertEvaluation,
    TradingAlertRepository,
    TradingAlertTrigger,
    TradingAlertUpdate,
    default_alert_repository,
)


class TradingAlertListResponse(BaseModel):
    alerts: list[TradingAlert]


class TradingAlertTriggerListResponse(BaseModel):
    triggers: list[TradingAlertTrigger]


AlertRepositoryFactory = Callable[[], TradingAlertRepository]


def create_trading_alert_router(
    repository_factory: AlertRepositoryFactory = default_alert_repository,
) -> APIRouter:
    router = APIRouter(prefix="/api/trading/alerts", tags=["trading-alerts"])

    @router.get("", response_model=TradingAlertListResponse)
    async def list_alerts(
        limit: int = Query(default=200, ge=1, le=500),
    ) -> TradingAlertListResponse:
        return TradingAlertListResponse(
            alerts=repository_factory().list_alerts(limit=limit)
        )

    @router.post("", response_model=TradingAlert, status_code=201)
    async def create_alert(request: TradingAlertCreate) -> TradingAlert:
        try:
            return repository_factory().create(request)
        except RevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/triggers", response_model=TradingAlertTriggerListResponse)
    async def list_triggers(
        limit: int = Query(default=200, ge=1, le=500),
    ) -> TradingAlertTriggerListResponse:
        return TradingAlertTriggerListResponse(
            triggers=repository_factory().list_triggers(limit=limit)
        )

    @router.post("/evaluate", response_model=TradingAlertTriggerListResponse)
    async def evaluate_alerts(
        request: TradingAlertEvaluation,
    ) -> TradingAlertTriggerListResponse:
        return TradingAlertTriggerListResponse(
            triggers=repository_factory().evaluate(request)
        )

    @router.put("/{alert_id}", response_model=TradingAlert)
    async def update_alert(
        alert_id: str,
        request: TradingAlertUpdate,
        if_match: int = Header(alias="If-Match", ge=1),
    ) -> TradingAlert:
        try:
            return repository_factory().update(
                alert_id,
                request,
                expected_revision=if_match,
            )
        except RevisionConflict as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "revision_conflict",
                    "message": str(exc),
                },
            ) from exc

    @router.delete("/{alert_id}", response_model=TradingAlert)
    async def archive_alert(
        alert_id: str,
        if_match: int = Header(alias="If-Match", ge=1),
    ) -> TradingAlert:
        try:
            return repository_factory().archive(
                alert_id,
                expected_revision=if_match,
            )
        except RevisionConflict as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "revision_conflict",
                    "message": str(exc),
                },
            ) from exc

    return router
