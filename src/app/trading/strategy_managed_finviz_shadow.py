from __future__ import annotations

"""Idempotent startup provisioning for the managed interday SHADOW profile."""

import os
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.persistence.errors import RevisionConflict

from .paper import PaperAccountCreate
from .paper_repository import TradingPaperRepository
from .strategies.models import StochRsi5mConfig, StrategyRiskProfile
from .strategy_repository import (
    TradingStrategyConfigDocument,
    TradingStrategyRepository,
)
from .strategy_v2_qualification import managed_finviz_v2_config
from .trade_logging import trade_log


INTERDAY_TRADING_STRATEGY_ID = "interday-trading-strategy-shadow"
# Compatibility name for callers that still refer to the managed Finviz
# provisioner. The durable strategy identity is the interday group ID above.
MANAGED_FINVIZ_SHADOW_STRATEGY_ID = INTERDAY_TRADING_STRATEGY_ID
MANAGED_FINVIZ_SHADOW_ACCOUNT_ID = "omnix-finviz-shadow"
STOCH_RSI_GUARDED_STRATEGY_ID = "stoch-rsi-5min-guarded-v1"
_MANAGED_ACCOUNT_NAME = "Omnix Finviz SHADOW"
_MAX_UPDATE_ATTEMPTS = 3

# The first four are embedded research arms of the parent configuration. The
# final three are durable child strategy configurations linked by
# TradingStrategyConfigDocument.parent_strategy_id.
INTERDAY_TRADING_SUBSTRATEGY_KEYS = (
    "deterministic-v2",
    "stoch-trend-capture",
    "ai-every-minute",
    "ai-event-driven",
    "stoch-rsi-5min",
    STOCH_RSI_GUARDED_STRATEGY_ID,
    "gap-pullback-v2-prospective-20260825",
)


class ManagedFinvizShadowProvisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy_id: str = MANAGED_FINVIZ_SHADOW_STRATEGY_ID
    account_id: str | None = None
    action: Literal[
        "created",
        "updated",
        "unchanged",
        "archived_suppressed",
        "disabled",
    ]
    enabled: bool
    mode: Literal["shadow", "auto_paper"] = "shadow"
    detail: str | None = None


def _flag(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def managed_finviz_shadow_autoprovision_enabled() -> bool:
    """Production defaults on; legacy tests remain opt-in."""

    if os.environ.get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return _flag("OMNIX_TRADING_FINVIZ_SHADOW_AUTOPROVISION_IN_TESTS", "0")
    return _flag("OMNIX_TRADING_FINVIZ_SHADOW_AUTOPROVISION", "1")


def managed_finviz_shadow_config():
    """Server-canonical equivalent of the UI Finviz Learning V2 preset."""

    return managed_finviz_v2_config()


def managed_finviz_shadow_document(account_id: str) -> TradingStrategyConfigDocument:
    return TradingStrategyConfigDocument(
        strategy_id=MANAGED_FINVIZ_SHADOW_STRATEGY_ID,
        account_id=account_id,
        strategy_kind="gap_pullback_v1",
        strategy_version="2.0.0",
        mode="shadow",
        active_universe_id=None,
        config=managed_finviz_shadow_config(),
        risk=StrategyRiskProfile(),
        enabled=True,
    )


def managed_stoch_rsi_guarded_document(account_id: str) -> TradingStrategyConfigDocument:
    """Canonical child configuration for the guarded Stoch RSI research arm.

    The child intentionally does not create a separate morning archive. Runtime
    resolution reads the managed interday parent's immutable benchmark archive,
    so the guarded arm is compared against the exact same frozen cohort.
    """

    parent = managed_finviz_shadow_config()
    config = StochRsi5mConfig(
        policy_profile="guarded_v1",
        universe_scan_time_et=parent.universe_scan_time_et,
        universe_discovery_source=parent.universe_discovery_source,
        auto_archive_daily_universe=False,
        universe_archive_grace_minutes=parent.universe_archive_grace_minutes,
        universe_discovery_count=parent.universe_discovery_count,
        minimum_gap_pct=parent.minimum_gap_pct,
        minimum_price=parent.minimum_price,
        maximum_price=parent.maximum_price,
    )
    return TradingStrategyConfigDocument(
        strategy_id=STOCH_RSI_GUARDED_STRATEGY_ID,
        parent_strategy_id=INTERDAY_TRADING_STRATEGY_ID,
        account_id=account_id,
        strategy_kind="stoch_rsi_5m_v1",
        strategy_version="1.0.0",
        mode="shadow",
        active_universe_id=None,
        config=config,
        risk=StrategyRiskProfile(),
        enabled=True,
    )


def _managed_initial_cash() -> Decimal:
    raw = os.environ.get("OMNIX_TRADING_FINVIZ_SHADOW_INITIAL_CASH", "1000")
    value = Decimal(raw)
    if value <= 0:
        raise ValueError("managed_finviz_shadow_initial_cash_must_be_positive")
    return value


def _resolve_account(paper_repository: TradingPaperRepository) -> str:
    requested = os.environ.get("OMNIX_TRADING_FINVIZ_SHADOW_ACCOUNT_ID", "").strip()
    managed_id = requested or MANAGED_FINVIZ_SHADOW_ACCOUNT_ID
    accounts = paper_repository.list_accounts(limit=500)
    by_id = {account.account_id: account for account in accounts}

    existing = by_id.get(managed_id)
    if existing is not None:
        # SHADOW never places orders, so a disabled paper account is still a
        # valid durable FK/evidence owner. Startup must not silently re-enable
        # an operator-disabled account.
        return existing.account_id

    if requested:
        raise ValueError(f"managed_finviz_shadow_account_not_found:{requested}")

    request = PaperAccountCreate(
        account_id=MANAGED_FINVIZ_SHADOW_ACCOUNT_ID,
        name=_MANAGED_ACCOUNT_NAME,
        initial_cash=_managed_initial_cash(),
        commission_bps=Decimal("0"),
    )
    try:
        snapshot = paper_repository.create_account(request)
    except Exception:
        # Multi-worker startup can race here. If another worker created the
        # stable managed account first, converge on that durable row.
        raced = {
            account.account_id: account
            for account in paper_repository.list_accounts(limit=500)
        }.get(MANAGED_FINVIZ_SHADOW_ACCOUNT_ID)
        if raced is None:
            raise
        return raced.account_id
    return snapshot.account.account_id


def _desired_for_current(
    current: TradingStrategyConfigDocument,
    desired_shadow: TradingStrategyConfigDocument,
) -> TradingStrategyConfigDocument:
    """Preserve an already-authorized AUTO PAPER promotion across restart.

    Startup is allowed to restore the managed research profile, but it must
    never grant AUTO PAPER authority. The only promoted state preserved here is
    one that is already enabled and persisted as auto_paper; the strategy
    runtime re-checks the V2 qualification fingerprint before every execution
    cycle. An operator-disabled/off strategy falls back to SHADOW on startup.
    """

    if current.mode == "auto_paper" and current.enabled:
        return desired_shadow.model_copy(
            update={
                "mode": "auto_paper",
                # The managed profile consumes the current day's immutable
                # strategy-owned archive at runtime. Carrying yesterday's
                # explicit universe across restart would make the next session
                # fail with UNIVERSE_SESSION_MISMATCH.
                "active_universe_id": None,
            }
        )
    return desired_shadow


def _managed_fields_match(
    current: TradingStrategyConfigDocument,
    desired: TradingStrategyConfigDocument,
) -> bool:
    return (
        current.account_id == desired.account_id
        and current.parent_strategy_id == desired.parent_strategy_id
        and current.strategy_kind == desired.strategy_kind
        and current.strategy_version == desired.strategy_version
        and current.mode == desired.mode
        and current.active_universe_id == desired.active_universe_id
        and current.config == desired.config
        and current.risk == desired.risk
        and current.enabled is True
    )


def _ensure_guarded_child(
    strategy_repo: TradingStrategyRepository,
    *,
    account_id: str,
) -> None:
    """Create/update the guarded child arm without resurrecting an archive."""

    desired = managed_stoch_rsi_guarded_document(account_id)
    for attempt in range(_MAX_UPDATE_ATTEMPTS):
        try:
            current = strategy_repo.get_config(STOCH_RSI_GUARDED_STRATEGY_ID)
        except ValueError as exc:
            if str(exc) != "strategy_config_not_found":
                raise
            try:
                created = strategy_repo.create_config(desired)
            except Exception:
                try:
                    current = strategy_repo.get_config(STOCH_RSI_GUARDED_STRATEGY_ID)
                except ValueError as reread_exc:
                    if str(reread_exc) == "strategy_config_not_found":
                        raise
                    raise
            else:
                trade_log(
                    "auto_trading",
                    "managed_interday_child_provisioned",
                    strategy_id=created.strategy_id,
                    parent_strategy_id=created.parent_strategy_id,
                    account_id=created.account_id,
                    action="created",
                    mode=created.mode,
                    policy_profile=created.config.policy_profile,
                )
                return

        if current.archived_at is not None:
            trade_log(
                "auto_trading",
                "managed_interday_child_provision_suppressed",
                strategy_id=current.strategy_id,
                parent_strategy_id=current.parent_strategy_id,
                account_id=current.account_id,
                action="archived_suppressed",
                archived_at=current.archived_at,
            )
            return

        if _managed_fields_match(current, desired):
            return

        replacement = desired.model_copy(
            update={
                "revision": current.revision,
                "created_at": current.created_at,
                "updated_at": current.updated_at,
            }
        )
        try:
            updated = strategy_repo.update_config(
                STOCH_RSI_GUARDED_STRATEGY_ID,
                replacement,
                expected_revision=current.revision,
            )
        except RevisionConflict:
            if attempt + 1 >= _MAX_UPDATE_ATTEMPTS:
                raise
            continue

        trade_log(
            "auto_trading",
            "managed_interday_child_provisioned",
            strategy_id=updated.strategy_id,
            parent_strategy_id=updated.parent_strategy_id,
            account_id=updated.account_id,
            action="updated",
            mode=updated.mode,
            policy_profile=updated.config.policy_profile,
            revision=updated.revision,
        )
        return

    raise RuntimeError("managed_stoch_rsi_guarded_provision_retry_exhausted")


def provision_managed_finviz_shadow_strategy(
    *,
    strategy_repository: TradingStrategyRepository | None = None,
    paper_repository: TradingPaperRepository | None = None,
) -> ManagedFinvizShadowProvisionResult:
    """Create or restore the managed Finviz profile and guarded child arm.

    New/disabled/off parent profiles start in SHADOW. If the exact managed
    strategy was already promoted to enabled AUTO PAPER through the normal
    qualification and review path, startup preserves that mode instead of
    silently demoting it. The guarded Stoch RSI arm is always SHADOW-only.
    Explicitly archived parent/child configs are never resurrected.
    """

    if not managed_finviz_shadow_autoprovision_enabled():
        return ManagedFinvizShadowProvisionResult(
            action="disabled",
            enabled=False,
            detail="autoprovision_disabled",
        )

    strategy_repo = strategy_repository or TradingStrategyRepository()
    paper_repo = paper_repository or TradingPaperRepository()

    try:
        preexisting = strategy_repo.get_config(
            MANAGED_FINVIZ_SHADOW_STRATEGY_ID
        )
    except ValueError as exc:
        if str(exc) != "strategy_config_not_found":
            raise
    else:
        if preexisting.archived_at is not None:
            return ManagedFinvizShadowProvisionResult(
                account_id=preexisting.account_id,
                action="archived_suppressed",
                enabled=False,
                detail="explicit_operator_archive",
            )

    account_id = _resolve_account(paper_repo)
    desired = managed_finviz_shadow_document(account_id)

    for attempt in range(_MAX_UPDATE_ATTEMPTS):
        try:
            current = strategy_repo.get_config(MANAGED_FINVIZ_SHADOW_STRATEGY_ID)
        except ValueError as exc:
            if str(exc) != "strategy_config_not_found":
                raise
            try:
                created = strategy_repo.create_config(desired)
            except Exception:
                # A second startup worker may have inserted the stable strategy
                # ID between the read and create. Re-read and converge instead
                # of treating that harmless race as a provisioning failure.
                try:
                    current = strategy_repo.get_config(
                        MANAGED_FINVIZ_SHADOW_STRATEGY_ID
                    )
                except ValueError as reread_exc:
                    if str(reread_exc) == "strategy_config_not_found":
                        raise
                    raise
            else:
                _ensure_guarded_child(strategy_repo, account_id=created.account_id)
                trade_log(
                    "auto_trading",
                    "managed_finviz_shadow_provisioned",
                    strategy_id=created.strategy_id,
                    account_id=created.account_id,
                    action="created",
                    mode=created.mode,
                    enabled=created.enabled,
                )
                return ManagedFinvizShadowProvisionResult(
                    account_id=created.account_id,
                    action="created",
                    enabled=created.enabled,
                    mode=created.mode,
                )

        if current.archived_at is not None:
            trade_log(
                "auto_trading",
                "managed_finviz_shadow_provision_suppressed",
                strategy_id=current.strategy_id,
                account_id=current.account_id,
                action="archived_suppressed",
                archived_at=current.archived_at,
            )
            return ManagedFinvizShadowProvisionResult(
                account_id=current.account_id,
                action="archived_suppressed",
                enabled=False,
                detail="explicit_operator_archive",
            )

        desired_for_current = _desired_for_current(current, desired)
        if _managed_fields_match(current, desired_for_current):
            _ensure_guarded_child(strategy_repo, account_id=current.account_id)
            return ManagedFinvizShadowProvisionResult(
                account_id=current.account_id,
                action="unchanged",
                enabled=True,
                mode=current.mode,
            )

        replacement = desired_for_current.model_copy(
            update={
                "revision": current.revision,
                "created_at": current.created_at,
                "updated_at": current.updated_at,
            }
        )
        try:
            updated = strategy_repo.update_config(
                MANAGED_FINVIZ_SHADOW_STRATEGY_ID,
                replacement,
                expected_revision=current.revision,
            )
        except RevisionConflict:
            if attempt + 1 >= _MAX_UPDATE_ATTEMPTS:
                raise
            continue

        _ensure_guarded_child(strategy_repo, account_id=updated.account_id)
        trade_log(
            "auto_trading",
            "managed_finviz_shadow_provisioned",
            strategy_id=updated.strategy_id,
            account_id=updated.account_id,
            action="updated",
            mode=updated.mode,
            enabled=updated.enabled,
            revision=updated.revision,
        )
        return ManagedFinvizShadowProvisionResult(
            account_id=updated.account_id,
            action="updated",
            enabled=updated.enabled,
            mode=updated.mode,
        )

    raise RuntimeError("managed_finviz_shadow_provision_retry_exhausted")


__all__ = [
    "INTERDAY_TRADING_STRATEGY_ID",
    "INTERDAY_TRADING_SUBSTRATEGY_KEYS",
    "MANAGED_FINVIZ_SHADOW_ACCOUNT_ID",
    "MANAGED_FINVIZ_SHADOW_STRATEGY_ID",
    "STOCH_RSI_GUARDED_STRATEGY_ID",
    "ManagedFinvizShadowProvisionResult",
    "managed_finviz_shadow_autoprovision_enabled",
    "managed_finviz_shadow_config",
    "managed_finviz_shadow_document",
    "managed_stoch_rsi_guarded_document",
    "provision_managed_finviz_shadow_strategy",
]
