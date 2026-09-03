from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.persistence.errors import RevisionConflict

from .strategy_repository import TradingStrategyRepository
from .trade_logging import trade_log


OBSOLETE_GAP_PULLBACK_STRATEGY_ID = "gap-pullback-1787099664227"


@dataclass(frozen=True)
class LegacyStrategyRetirementResult:
    strategy_id: str
    action: Literal[
        "archived",
        "already_archived",
        "not_found",
        "blocked_auto_paper",
        "blocked_active_protections",
        "revision_conflict",
    ]
    detail: str | None = None


def retire_obsolete_gap_pullback_strategy(
    repository: TradingStrategyRepository,
) -> LegacyStrategyRetirementResult:
    """Soft-archive the one obsolete Yahoo gap-pullback strategy instance.

    This is intentionally scoped to the exact historical strategy ID that was
    superseded by the managed Finviz V2 profile. Evidence remains durable because
    ``delete_config`` is a soft archive. Safety wins over cleanup: AUTO PAPER or
    any active protection blocks retirement so an in-flight position can never
    lose its protection monitor merely to silence legacy diagnostics.
    """

    strategy_id = OBSOLETE_GAP_PULLBACK_STRATEGY_ID
    try:
        config = repository.get_config(strategy_id)
    except ValueError as exc:
        if str(exc) != "strategy_config_not_found":
            raise
        return LegacyStrategyRetirementResult(strategy_id, "not_found")

    if config.archived_at is not None:
        return LegacyStrategyRetirementResult(strategy_id, "already_archived")

    if config.mode == "auto_paper":
        result = LegacyStrategyRetirementResult(
            strategy_id,
            "blocked_auto_paper",
            "AUTO PAPER must be explicitly disabled before archival",
        )
        trade_log(
            "auto_trading",
            "legacy_strategy_retirement_blocked",
            strategy_id=strategy_id,
            reason=result.action,
            detail=result.detail,
        )
        return result

    active_protections = repository.list_protections(strategy_id, active_only=True)
    if active_protections:
        result = LegacyStrategyRetirementResult(
            strategy_id,
            "blocked_active_protections",
            f"active_protection_count={len(active_protections)}",
        )
        trade_log(
            "auto_trading",
            "legacy_strategy_retirement_blocked",
            strategy_id=strategy_id,
            reason=result.action,
            detail=result.detail,
        )
        return result

    try:
        repository.delete_config(strategy_id, expected_revision=config.revision)
    except RevisionConflict as exc:
        result = LegacyStrategyRetirementResult(
            strategy_id,
            "revision_conflict",
            str(exc),
        )
        trade_log(
            "auto_trading",
            "legacy_strategy_retirement_blocked",
            strategy_id=strategy_id,
            reason=result.action,
            detail=result.detail,
        )
        return result

    trade_log(
        "auto_trading",
        "legacy_strategy_archived",
        strategy_id=strategy_id,
        prior_mode=config.mode,
        prior_enabled=config.enabled,
        reason="superseded_by_managed_finviz_v2",
    )
    return LegacyStrategyRetirementResult(strategy_id, "archived")


__all__ = [
    "LegacyStrategyRetirementResult",
    "OBSOLETE_GAP_PULLBACK_STRATEGY_ID",
    "retire_obsolete_gap_pullback_strategy",
]
