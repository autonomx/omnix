
from __future__ import annotations

import json

from app.persistence.tenant import TenantContext, local_tenant_context
from app.persistence.unit_of_work import unit_of_work

from .strategy_repository import StrategyEvent
from .strategy_solana_ai import (
    SOLANA_AI_STRATEGY_ID,
    SOLANA_BINDING_ID,
    SOLANA_INSTRUMENT_ID,
)


SOLANA_AI_STRATEGY_VERSION = "solana-ai-1m-v1"
SOLANA_AI_STRATEGY_KIND = "solana_ai_1m_shadow"
SOLANA_AI_DISPLAY_NAME = "Solana AI 1m Shadow"


class SolanaAIStrategyRepository:
    """Durable configuration identity and decision history for the SOL AI shadow strategy.

    This repository is intentionally separate from the gap-pullback strategy tables:
    those tables validate a GapPullbackConfig and require a paper-account parent,
    neither of which belongs to this research-only crypto strategy.
    """

    def __init__(
        self,
        *,
        context: TenantContext | None = None,
        uow_factory=unit_of_work,
    ) -> None:
        self.context = context or local_tenant_context()
        self.uow_factory = uow_factory

    def _upsert_strategy(self, connection, *, enabled: bool) -> None:
        connection.execute(
            """
            INSERT INTO omnix_trading_solana_ai_strategies (
                workspace_id, strategy_id, strategy_kind, strategy_version,
                display_name, instrument_id, binding_id, chart_interval, mode, enabled
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'shadow', %s)
            ON CONFLICT (workspace_id, strategy_id) DO UPDATE
               SET strategy_kind = EXCLUDED.strategy_kind,
                   strategy_version = EXCLUDED.strategy_version,
                   display_name = EXCLUDED.display_name,
                   instrument_id = EXCLUDED.instrument_id,
                   binding_id = EXCLUDED.binding_id,
                   chart_interval = EXCLUDED.chart_interval,
                   mode = EXCLUDED.mode,
                   enabled = EXCLUDED.enabled,
                   updated_at = CURRENT_TIMESTAMP
            """,
            (
                self.context.workspace_id,
                SOLANA_AI_STRATEGY_ID,
                SOLANA_AI_STRATEGY_KIND,
                SOLANA_AI_STRATEGY_VERSION,
                SOLANA_AI_DISPLAY_NAME,
                SOLANA_INSTRUMENT_ID,
                SOLANA_BINDING_ID,
                "1m",
                bool(enabled),
            ),
        )

    def ensure_strategy(self, *, enabled: bool) -> None:
        with self.uow_factory() as uow:
            self._upsert_strategy(uow.connection, enabled=enabled)
            uow.commit()

    def append_decision(self, event: StrategyEvent, *, enabled: bool) -> bool:
        if event.strategy_id != SOLANA_AI_STRATEGY_ID:
            raise ValueError("solana_ai_strategy_id_mismatch")
        if event.event_type != "solana_ai_decision":
            raise ValueError("solana_ai_event_type_mismatch")
        with self.uow_factory() as uow:
            # The parent and event are committed atomically so a freshly deployed
            # strategy cannot race its own first decision against configuration setup.
            self._upsert_strategy(uow.connection, enabled=enabled)
            inserted = uow.connection.execute(
                """
                INSERT INTO omnix_trading_solana_ai_decisions (
                    workspace_id, strategy_id, event_id, instrument_id, state,
                    observed_at, idempotency_key, payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (workspace_id, strategy_id, idempotency_key) DO NOTHING
                RETURNING event_id
                """,
                (
                    self.context.workspace_id,
                    event.strategy_id,
                    event.event_id,
                    event.instrument_id,
                    event.state,
                    event.observed_at,
                    event.idempotency_key,
                    json.dumps(event.payload, default=str),
                ),
            ).fetchone()
            uow.commit()
        return inserted is not None

    def recent_decisions(self, *, limit: int = 50) -> list[StrategyEvent]:
        normalized_limit = max(1, min(int(limit), 200))
        with self.uow_factory() as uow:
            rows = uow.connection.execute(
                """
                SELECT event_id, instrument_id, state, observed_at, idempotency_key, payload
                  FROM omnix_trading_solana_ai_decisions
                 WHERE workspace_id = %s AND strategy_id = %s
                 ORDER BY observed_at DESC, created_at DESC, event_id DESC
                 LIMIT %s
                """,
                (self.context.workspace_id, SOLANA_AI_STRATEGY_ID, normalized_limit),
            ).fetchall()
        return [
            StrategyEvent(
                strategy_id=SOLANA_AI_STRATEGY_ID,
                event_id=str(row[0]),
                instrument_id=str(row[1]),
                event_type="solana_ai_decision",
                state=str(row[2]),
                reason_code=None,
                observed_at=row[3],
                idempotency_key=str(row[4]),
                payload=dict(row[5] or {}),
            )
            for row in rows
        ]

    def decision_counts(self) -> tuple[int, int]:
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                """
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE state IN ('enter_long', 'exit_long'))
                  FROM omnix_trading_solana_ai_decisions
                 WHERE workspace_id = %s AND strategy_id = %s
                """,
                (self.context.workspace_id, SOLANA_AI_STRATEGY_ID),
            ).fetchone()
        if row is None:
            return (0, 0)
        return (int(row[0] or 0), int(row[1] or 0))


def default_solana_ai_strategy_repository() -> SolanaAIStrategyRepository:
    return SolanaAIStrategyRepository()


__all__ = [
    "SOLANA_AI_DISPLAY_NAME",
    "SOLANA_AI_STRATEGY_KIND",
    "SOLANA_AI_STRATEGY_VERSION",
    "SolanaAIStrategyRepository",
    "default_solana_ai_strategy_repository",
]
