from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.persistence.errors import RevisionConflict
from app.persistence.tenant import TenantContext, local_tenant_context
from app.persistence.unit_of_work import PostgresUnitOfWork, unit_of_work

from .gapper_dataset import GapperUniverseSnapshot
from .strategies.models import GapPullbackConfig, StrategyMode, StrategyRiskProfile


class TradingStrategyConfigDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str = Field(min_length=1, max_length=200)
    account_id: str = Field(min_length=1, max_length=200)
    strategy_kind: Literal["gap_pullback_v1"] = "gap_pullback_v1"
    strategy_version: str = "1.0.0"
    mode: StrategyMode = "off"
    active_universe_id: str | None = None
    config: GapPullbackConfig = Field(default_factory=GapPullbackConfig)
    risk: StrategyRiskProfile = Field(default_factory=StrategyRiskProfile)
    enabled: bool = True
    revision: int = Field(default=1, ge=1)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class StrategyEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy_id: str
    event_id: str
    run_id: str | None = None
    instrument_id: str
    event_type: str
    state: str
    reason_code: str | None = None
    observed_at: datetime
    idempotency_key: str
    payload: dict[str, object] = Field(default_factory=dict)


class StrategyProtection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    protection_id: str
    account_id: str
    instrument_id: str
    entry_order_id: str
    exit_order_id: str | None = None
    stop_price: Decimal = Field(gt=0)
    target_price: Decimal = Field(gt=0)
    quantity: Decimal = Field(gt=0)
    status: Literal["pending_entry", "active", "exit_submitted", "closed", "cancelled"] = "pending_entry"
    trigger_reason: str | None = None
    revision: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None


def _config(row) -> TradingStrategyConfigDocument:
    return TradingStrategyConfigDocument(
        strategy_id=str(row[0]),
        account_id=str(row[1]),
        strategy_kind=str(row[2]),
        strategy_version=str(row[3]),
        mode=str(row[4]),
        active_universe_id=str(row[5]) if row[5] is not None else None,
        config=GapPullbackConfig.model_validate(row[6]),
        risk=StrategyRiskProfile.model_validate(row[7]),
        enabled=bool(row[8]),
        revision=int(row[9]),
        created_at=row[10],
        updated_at=row[11],
    )


def _protection(row) -> StrategyProtection:
    return StrategyProtection(
        strategy_id=str(row[0]),
        protection_id=str(row[1]),
        account_id=str(row[2]),
        instrument_id=str(row[3]),
        entry_order_id=str(row[4]),
        exit_order_id=str(row[5]) if row[5] is not None else None,
        stop_price=Decimal(row[6]),
        target_price=Decimal(row[7]),
        quantity=Decimal(row[8]),
        status=str(row[9]),
        trigger_reason=str(row[10]) if row[10] is not None else None,
        revision=int(row[11]),
        created_at=row[12],
        updated_at=row[13],
    )


_CONFIG_COLUMNS = """
strategy_id, account_id, strategy_kind, strategy_version, mode,
active_universe_id, config, risk, enabled, revision, created_at, updated_at
"""
_PROTECTION_COLUMNS = """
strategy_id, protection_id, account_id, instrument_id, entry_order_id,
exit_order_id, stop_price, target_price, quantity, status, trigger_reason,
revision, created_at, updated_at
"""


class TradingStrategyRepository:
    def __init__(
        self,
        *,
        context: TenantContext | None = None,
        uow_factory=unit_of_work,
    ) -> None:
        self.context = context or local_tenant_context()
        self.uow_factory = uow_factory

    def create_config(self, document: TradingStrategyConfigDocument) -> TradingStrategyConfigDocument:
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                f"""
                INSERT INTO omnix_trading_strategy_configs (
                    workspace_id, strategy_id, account_id, owner_user_id,
                    strategy_kind, strategy_version, mode, active_universe_id,
                    config, risk, enabled
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
                RETURNING {_CONFIG_COLUMNS}
                """,
                (
                    self.context.workspace_id,
                    document.strategy_id,
                    document.account_id,
                    self.context.user_id,
                    document.strategy_kind,
                    document.strategy_version,
                    document.mode,
                    document.active_universe_id,
                    json.dumps(document.config.model_dump(mode="json")),
                    json.dumps(document.risk.model_dump(mode="json")),
                    document.enabled,
                ),
            ).fetchone()
            uow.commit()
            return _config(row)

    def update_config(
        self,
        strategy_id: str,
        document: TradingStrategyConfigDocument,
        *,
        expected_revision: int,
    ) -> TradingStrategyConfigDocument:
        if strategy_id != document.strategy_id:
            raise ValueError("strategy_id_mismatch")
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                f"""
                UPDATE omnix_trading_strategy_configs
                   SET account_id = %s, strategy_kind = %s, strategy_version = %s,
                       mode = %s, active_universe_id = %s, config = %s::jsonb,
                       risk = %s::jsonb, enabled = %s,
                       revision = revision + 1, updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND strategy_id = %s AND revision = %s
                RETURNING {_CONFIG_COLUMNS}
                """,
                (
                    document.account_id,
                    document.strategy_kind,
                    document.strategy_version,
                    document.mode,
                    document.active_universe_id,
                    json.dumps(document.config.model_dump(mode="json")),
                    json.dumps(document.risk.model_dump(mode="json")),
                    document.enabled,
                    self.context.workspace_id,
                    strategy_id,
                    expected_revision,
                ),
            ).fetchone()
            if row is None:
                raise RevisionConflict("stale trading strategy configuration")
            uow.commit()
            return _config(row)

    def list_configs(self, *, active_only: bool = False) -> list[TradingStrategyConfigDocument]:
        predicate = "AND enabled = TRUE AND mode <> 'off'" if active_only else ""
        with self.uow_factory() as uow:
            rows = uow.connection.execute(
                f"""
                SELECT {_CONFIG_COLUMNS}
                  FROM omnix_trading_strategy_configs
                 WHERE workspace_id = %s {predicate}
                 ORDER BY updated_at DESC, strategy_id
                """,
                (self.context.workspace_id,),
            ).fetchall()
        return [_config(row) for row in rows]

    def get_config(self, strategy_id: str) -> TradingStrategyConfigDocument:
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                f"SELECT {_CONFIG_COLUMNS} FROM omnix_trading_strategy_configs WHERE workspace_id = %s AND strategy_id = %s",
                (self.context.workspace_id, strategy_id),
            ).fetchone()
        if row is None:
            raise ValueError("strategy_config_not_found")
        return _config(row)

    def save_universe(self, snapshot: GapperUniverseSnapshot) -> GapperUniverseSnapshot:
        with self.uow_factory() as uow:
            uow.connection.execute(
                """
                INSERT INTO omnix_trading_gapper_universes (
                    workspace_id, universe_id, session_date, evaluation_time,
                    discovery_source, source_fingerprint, candidates
                ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (workspace_id, source_fingerprint) DO NOTHING
                """,
                (
                    self.context.workspace_id,
                    snapshot.universe_id,
                    snapshot.session_date,
                    snapshot.evaluation_time,
                    snapshot.discovery_source,
                    snapshot.source_fingerprint,
                    json.dumps([item.model_dump(mode="json") for item in snapshot.candidates]),
                ),
            )
            uow.commit()
        return snapshot

    def get_universe(self, universe_id: str) -> GapperUniverseSnapshot:
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                """
                SELECT universe_id, session_date, evaluation_time, discovery_source,
                       source_fingerprint, candidates
                  FROM omnix_trading_gapper_universes
                 WHERE workspace_id = %s AND universe_id = %s
                """,
                (self.context.workspace_id, universe_id),
            ).fetchone()
        if row is None:
            raise ValueError("gapper_universe_not_found")
        return GapperUniverseSnapshot.model_validate(
            {
                "universe_id": row[0],
                "session_date": row[1],
                "evaluation_time": row[2],
                "discovery_source": row[3],
                "source_fingerprint": row[4],
                "candidates": row[5],
            }
        )

    def append_event(self, event: StrategyEvent) -> bool:
        with self.uow_factory() as uow:
            inserted = uow.connection.execute(
                """
                INSERT INTO omnix_trading_strategy_events (
                    workspace_id, strategy_id, event_id, run_id, instrument_id,
                    event_type, state, reason_code, observed_at, idempotency_key, payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (workspace_id, strategy_id, idempotency_key) DO NOTHING
                RETURNING event_id
                """,
                (
                    self.context.workspace_id,
                    event.strategy_id,
                    event.event_id,
                    event.run_id,
                    event.instrument_id,
                    event.event_type,
                    event.state,
                    event.reason_code,
                    event.observed_at,
                    event.idempotency_key,
                    json.dumps(event.payload, default=str),
                ),
            ).fetchone()
            uow.commit()
        return inserted is not None

    def recent_events(self, strategy_id: str, limit: int = 200) -> list[StrategyEvent]:
        with self.uow_factory() as uow:
            rows = uow.connection.execute(
                """
                SELECT strategy_id, event_id, run_id, instrument_id, event_type,
                       state, reason_code, observed_at, idempotency_key, payload
                  FROM omnix_trading_strategy_events
                 WHERE workspace_id = %s AND strategy_id = %s
                 ORDER BY observed_at DESC, created_at DESC LIMIT %s
                """,
                (self.context.workspace_id, strategy_id, limit),
            ).fetchall()
        return [
            StrategyEvent(
                strategy_id=row[0], event_id=row[1], run_id=row[2], instrument_id=row[3],
                event_type=row[4], state=row[5], reason_code=row[6], observed_at=row[7],
                idempotency_key=row[8], payload=row[9],
            )
            for row in rows
        ]

    def save_protection(self, protection: StrategyProtection) -> StrategyProtection:
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                f"""
                INSERT INTO omnix_trading_strategy_protections (
                    workspace_id, strategy_id, protection_id, account_id,
                    instrument_id, entry_order_id, exit_order_id, stop_price,
                    target_price, quantity, status, trigger_reason
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (workspace_id, strategy_id, entry_order_id) DO UPDATE
                   SET exit_order_id = EXCLUDED.exit_order_id,
                       stop_price = EXCLUDED.stop_price,
                       target_price = EXCLUDED.target_price,
                       quantity = EXCLUDED.quantity,
                       status = EXCLUDED.status,
                       trigger_reason = EXCLUDED.trigger_reason,
                       revision = omnix_trading_strategy_protections.revision + 1,
                       updated_at = CURRENT_TIMESTAMP
                RETURNING {_PROTECTION_COLUMNS}
                """,
                (
                    self.context.workspace_id, protection.strategy_id, protection.protection_id,
                    protection.account_id, protection.instrument_id, protection.entry_order_id,
                    protection.exit_order_id, protection.stop_price, protection.target_price,
                    protection.quantity, protection.status, protection.trigger_reason,
                ),
            ).fetchone()
            uow.commit()
            return _protection(row)

    def list_protections(self, strategy_id: str, *, active_only: bool = True) -> list[StrategyProtection]:
        predicate = "AND status IN ('pending_entry', 'active', 'exit_submitted')" if active_only else ""
        with self.uow_factory() as uow:
            rows = uow.connection.execute(
                f"""
                SELECT {_PROTECTION_COLUMNS}
                  FROM omnix_trading_strategy_protections
                 WHERE workspace_id = %s AND strategy_id = %s {predicate}
                 ORDER BY created_at
                """,
                (self.context.workspace_id, strategy_id),
            ).fetchall()
        return [_protection(row) for row in rows]


def default_strategy_repository() -> TradingStrategyRepository:
    return TradingStrategyRepository()
