from __future__ import annotations

from collections.abc import Callable, Iterable

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from app.errors import LegacyPersistenceRetired
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
from .alerts_channels import (
    AVAILABLE_ALERT_CHANNELS,
    AlertSecretStore,
    ProtectedAlertSecretStore,
    unavailable_channels,
)


class TradingAlertListResponse(BaseModel):
    alerts: list[TradingAlert]


class TradingAlertTriggerListResponse(BaseModel):
    triggers: list[TradingAlertTrigger]


AlertRepositoryFactory = Callable[[], TradingAlertRepository]


def create_trading_alert_router(
    repository_factory: AlertRepositoryFactory = default_alert_repository,
    *,
    secret_store: AlertSecretStore | None = None,
    available_channels: Iterable[str] = AVAILABLE_ALERT_CHANNELS,
) -> APIRouter:
    router = APIRouter(prefix="/api/trading/alerts", tags=["trading-alerts"])
    channels = frozenset(available_channels)
    store: AlertSecretStore = secret_store or ProtectedAlertSecretStore()

    def prepare_channels(
        request: TradingAlertCreate | TradingAlertUpdate,
        repository: TradingAlertRepository,
        alert_id: str,
    ) -> None:
        missing = unavailable_channels(request.parameters.notification_channels, channels)
        if missing:
            raise HTTPException(status_code=422, detail=f"alert channel {missing[0]} is not available yet")
        webhook = request.parameters.delivery.webhook
        secret = request.webhook_secret
        if secret is not None and webhook is None:
            raise HTTPException(status_code=422, detail="webhook_secret needs parameters.delivery.webhook")
        if webhook is None:
            return
        workspace_id = repository.context.workspace_id
        if secret is None:
            webhook.has_secret = store.has(workspace_id, alert_id)
            return
        value = secret.get_secret_value().strip()
        try:
            store.save(workspace_id, alert_id, value or None)
        except LegacyPersistenceRetired as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        webhook.has_secret = bool(value)

    @router.get("", response_model=TradingAlertListResponse)
    def list_alerts(
        limit: int = Query(default=200, ge=1, le=500),
    ) -> TradingAlertListResponse:
        return TradingAlertListResponse(
            alerts=repository_factory().list_alerts(limit=limit)
        )

    @router.post("", response_model=TradingAlert, status_code=201)
    def create_alert(request: TradingAlertCreate) -> TradingAlert:
        repository = repository_factory()
        prepare_channels(request, repository, request.alert_id)
        try:
            return repository.create(request)
        except RevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/triggers", response_model=TradingAlertTriggerListResponse)
    def list_triggers(
        limit: int = Query(default=200, ge=1, le=500),
    ) -> TradingAlertTriggerListResponse:
        return TradingAlertTriggerListResponse(
            triggers=repository_factory().list_triggers(limit=limit)
        )

    @router.post("/evaluate", response_model=TradingAlertTriggerListResponse)
    def evaluate_alerts(
        request: TradingAlertEvaluation,
    ) -> TradingAlertTriggerListResponse:
        """Evaluate a pushed price against the instrument's alerts.

        Only alerts whose conditions all read one price field (close from
        ``observed_price``, or volume from ``observed_volume``) against value
        targets are evaluated: the alert's ``last_observed_value`` is the
        previous value and the pushed value the current one. Every other alert
        (indicators, percent change, trendlines, moving operators) is skipped;
        the server monitor evaluates those on bars. Frequency, cooldown and
        idempotency apply as for monitored alerts, with ``observed_at`` as the bar.
        """
        return TradingAlertTriggerListResponse(
            triggers=repository_factory().evaluate(request)
        )

    @router.put("/{alert_id}", response_model=TradingAlert)
    def update_alert(
        alert_id: str,
        request: TradingAlertUpdate,
        if_match: int = Header(alias="If-Match", ge=1),
    ) -> TradingAlert:
        repository = repository_factory()
        prepare_channels(request, repository, alert_id)
        try:
            return repository.update(
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
    def archive_alert(
        alert_id: str,
        if_match: int = Header(alias="If-Match", ge=1),
    ) -> TradingAlert:
        repository = repository_factory()
        try:
            archived = repository.archive(
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
        webhook = archived.parameters.delivery.webhook
        if webhook is not None and webhook.has_secret:
            store.save(repository.context.workspace_id, alert_id, None)
        return archived

    return router
