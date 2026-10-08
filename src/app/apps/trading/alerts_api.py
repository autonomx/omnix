from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass

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
    TradingAlertUnreadable,
    TradingAlertUpdate,
    default_alert_repository,
)
from .alerts_channels import (
    AVAILABLE_ALERT_CHANNELS,
    AlertWebhookStore,
    ProtectedAlertWebhookStore,
    alert_mutation_lock,
    alert_webhook_prefix,
    mask_webhook_url,
    unavailable_channels,
)

logger = logging.getLogger(__name__)


class TradingAlertListResponse(BaseModel):
    alerts: list[TradingAlert]
    # Stored alerts that no longer read; archive them with their revision.
    unreadable: list[TradingAlertUnreadable] = []


class TradingAlertTriggerListResponse(BaseModel):
    triggers: list[TradingAlertTrigger]


AlertRepositoryFactory = Callable[[], TradingAlertRepository]


@dataclass(frozen=True)
class _WebhookPlan:
    """Which protected-store reference an alert write will point at.

    ``ref`` is what the row will reference. ``written`` is a reference this
    request stored before the row write: it is removed again if the write
    fails, and after a successful write every other reference of the alert
    is removed. The row never references anything that was not stored first.
    """

    ref: str | None
    written: str | None
    previous: str | None


def _conflict(exc: RevisionConflict) -> HTTPException:
    return HTTPException(status_code=409, detail={"code": "revision_conflict", "message": str(exc)})


def create_trading_alert_router(
    repository_factory: AlertRepositoryFactory = default_alert_repository,
    *,
    webhook_store: AlertWebhookStore | None = None,
    available_channels: Iterable[str] = AVAILABLE_ALERT_CHANNELS,
) -> APIRouter:
    router = APIRouter(prefix="/api/trading/alerts", tags=["trading-alerts"])
    channels = frozenset(available_channels)
    store: AlertWebhookStore = webhook_store or ProtectedAlertWebhookStore()

    def plan_webhook(
        request: TradingAlertCreate | TradingAlertUpdate,
        previous: TradingAlert | None,
        workspace_id: str,
        alert_id: str,
    ) -> _WebhookPlan:
        missing = unavailable_channels(request.parameters.notification_channels, channels)
        if missing:
            raise HTTPException(status_code=422, detail=f"alert channel {missing[0]} is not available yet")
        webhook = request.parameters.delivery.webhook
        secret = request.webhook_secret
        previous_ref = previous.webhook_ref if previous is not None else None
        if secret is not None and webhook is None:
            raise HTTPException(status_code=422, detail="webhook_secret needs parameters.delivery.webhook")
        if webhook is None:
            return _WebhookPlan(ref=None, written=None, previous=previous_ref)
        stored = store.load(previous_ref) if previous_ref else None
        url = webhook.url or (stored or {}).get("url")
        if not url:
            raise HTTPException(status_code=422, detail="parameters.delivery.webhook.url is required")
        value = (stored or {}).get("secret", "") if secret is None else secret.get_secret_value().strip()
        webhook.url = None  # write-only: the protected store keeps it
        webhook.display_url = mask_webhook_url(url)
        webhook.has_secret = bool(value)
        if stored is not None and stored.get("url") == url and stored.get("secret", "") == value:
            return _WebhookPlan(ref=previous_ref, written=None, previous=previous_ref)
        if not store.available():
            raise HTTPException(status_code=422, detail="alert webhooks require an operating-system credential store")
        ref = f"{alert_webhook_prefix(workspace_id, alert_id)}{uuid.uuid4().hex}"
        try:
            store.save(ref, url, value)
        except LegacyPersistenceRetired as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("trading_alert_webhook_store_failed alert_id=%s", alert_id)
            raise HTTPException(status_code=503, detail="the alert webhook could not be stored; nothing was changed") from exc
        return _WebhookPlan(ref=ref, written=ref, previous=previous_ref)

    def prune_webhooks(workspace_id: str, alert_id: str, keep: str | None) -> None:
        """Best effort: a reference no row points at is unused, so a failure only leaves litter."""
        try:
            store.delete_alert(workspace_id, alert_id, keep=keep)
        except Exception:
            logger.warning("trading_alert_webhook_prune_failed alert_id=%s", alert_id, exc_info=True)

    def discard(ref: str, alert_id: str) -> None:
        """Best effort: remove a reference this request stored but no row took."""
        try:
            store.delete(ref)
        except Exception:
            logger.warning("trading_alert_webhook_cleanup_failed alert_id=%s", alert_id, exc_info=True)

    @router.get("", response_model=TradingAlertListResponse)
    def list_alerts(
        limit: int = Query(default=200, ge=1, le=500),
    ) -> TradingAlertListResponse:
        listing = repository_factory().list_alerts_report(limit=limit)
        return TradingAlertListResponse(alerts=listing.alerts, unreadable=listing.unreadable)

    @router.post("", response_model=TradingAlert, status_code=201)
    def create_alert(request: TradingAlertCreate) -> TradingAlert:
        repository = repository_factory()
        workspace_id = repository.context.workspace_id
        with alert_mutation_lock(workspace_id, request.alert_id):
            plan = plan_webhook(request, None, workspace_id, request.alert_id)
            try:
                created = repository.create(request, webhook_ref=plan.ref)
            except Exception as exc:
                if plan.written:
                    discard(plan.written, request.alert_id)
                if isinstance(exc, RevisionConflict):
                    raise HTTPException(status_code=409, detail=str(exc)) from exc
                raise
            # A new alert owns its id: webhooks left by an earlier alert with this id go.
            prune_webhooks(workspace_id, request.alert_id, keep=plan.ref)
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
        workspace_id = repository.context.workspace_id
        with alert_mutation_lock(workspace_id, alert_id):
            previous = repository.get(alert_id)
            if previous is None or previous.revision != if_match:
                raise _conflict(RevisionConflict(f"Trading alert expected revision {if_match}: {alert_id}"))
            plan = plan_webhook(request, previous, workspace_id, alert_id)
            try:
                updated = repository.update(alert_id, request, expected_revision=if_match, webhook_ref=plan.ref)
            except Exception as exc:
                if plan.written:
                    discard(plan.written, alert_id)
                if isinstance(exc, RevisionConflict):
                    raise _conflict(exc) from exc
                raise
            if plan.ref != plan.previous:
                # Rotated or removed: the old destination and secret stop existing.
                prune_webhooks(workspace_id, alert_id, keep=plan.ref)
            return updated

    @router.delete("/{alert_id}", response_model=TradingAlert)
    def archive_alert(
        alert_id: str,
        if_match: int = Header(alias="If-Match", ge=1),
    ) -> TradingAlert:
        repository = repository_factory()
        workspace_id = repository.context.workspace_id
        with alert_mutation_lock(workspace_id, alert_id):
            try:
                archived = repository.archive(alert_id, expected_revision=if_match)
            except RevisionConflict as exc:
                raise _conflict(exc) from exc
            prune_webhooks(workspace_id, alert_id, keep=None)
            return archived

    return router
