from __future__ import annotations

from collections.abc import Callable, Iterable

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
        previous: TradingAlert | None,
    ) -> str | None:
        """Check channels and set ``has_secret``; return the secret change to save.

        Nothing is written here: the secret store changes only after the
        alert itself was saved (``finish_channels``).
        """
        missing = unavailable_channels(request.parameters.notification_channels, channels)
        if missing:
            raise HTTPException(status_code=422, detail=f"alert channel {missing[0]} is not available yet")
        webhook = request.parameters.delivery.webhook
        secret = request.webhook_secret
        if secret is not None and webhook is None:
            raise HTTPException(status_code=422, detail="webhook_secret needs parameters.delivery.webhook")
        if webhook is None:
            return None
        if secret is None:
            previous_webhook = previous.parameters.delivery.webhook if previous is not None else None
            webhook.has_secret = previous_webhook is not None and previous_webhook.has_secret
            return None
        value = secret.get_secret_value().strip()
        if value and not store.available():
            raise HTTPException(
                status_code=422,
                detail="alert webhook secrets require an operating-system credential store",
            )
        webhook.has_secret = bool(value)
        return value

    def finish_channels(
        repository: TradingAlertRepository,
        alert_id: str,
        request: TradingAlertCreate | TradingAlertUpdate,
        previous: TradingAlert | None,
        secret: str | None,
    ) -> None:
        if secret is not None:
            store.save(repository.context.workspace_id, alert_id, secret or None)
            return
        previous_webhook = previous.parameters.delivery.webhook if previous is not None else None
        if request.parameters.delivery.webhook is None and previous_webhook is not None and previous_webhook.has_secret:
            store.save(repository.context.workspace_id, alert_id, None)

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
        secret = prepare_channels(request, None)
        try:
            created = repository.create(request)
        except RevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        finish_channels(repository, created.alert_id, request, None, secret)
        return created

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
        the server monitor evaluates those on bars. Alerts with a per-bar
        frequency (``once_per_bar``, ``once_per_bar_close``) are skipped too: a
        pushed price carries no bar. Other frequencies, cooldown and
        idempotency apply as for monitored alerts, with ``observed_at`` as the
        observation's time.
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
        previous = repository.get(alert_id)
        secret = prepare_channels(request, previous)
        try:
            updated = repository.update(
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
        finish_channels(repository, alert_id, request, previous, secret)
        return updated

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
