from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from decimal import Decimal
from typing import Protocol

from app.persistence.errors import RevisionConflict
from app.persistence.tenant import TenantContext, local_tenant_context
from app.persistence.unit_of_work import PostgresUnitOfWork, unit_of_work

from .paper import PaperAccountSnapshot
from .paper_repository import TradingPaperRepository


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> AbstractContextManager[PostgresUnitOfWork]: ...


class TradingPaperLifecycle:
    def __init__(
        self,
        *,
        context: TenantContext | None = None,
        uow_factory: UnitOfWorkFactory = unit_of_work,
        repository_factory: Callable[[], TradingPaperRepository] | None = None,
    ) -> None:
        self.context = context or local_tenant_context()
        self.uow_factory = uow_factory
        self.repository_factory = repository_factory or (
            lambda: TradingPaperRepository(
                context=self.context,
                uow_factory=self.uow_factory,
            )
        )

    def reset_account(
        self,
        account_id: str,
        *,
        initial_cash: Decimal,
        expected_revision: int,
    ) -> PaperAccountSnapshot:
        if initial_cash < 0:
            raise ValueError("initial_cash_must_be_non_negative")
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                """
                SELECT base_currency, revision
                  FROM omnix_trading_paper_accounts
                 WHERE workspace_id = %s AND account_id = %s
                 FOR UPDATE
                """,
                (self.context.workspace_id, account_id),
            ).fetchone()
            if row is None:
                raise ValueError(f"paper_account_not_found: {account_id}")
            if int(row[1]) != expected_revision:
                raise RevisionConflict(
                    f"Paper account expected revision {expected_revision}: {account_id}"
                )
            currency = str(row[0])
            for table in (
                "omnix_trading_paper_ledger",
                "omnix_trading_paper_fills",
                "omnix_trading_paper_orders",
                "omnix_trading_paper_positions",
                "omnix_trading_paper_balances",
            ):
                uow.connection.execute(
                    f"DELETE FROM {table} WHERE workspace_id = %s AND account_id = %s",
                    (self.context.workspace_id, account_id),
                )
            uow.connection.execute(
                """
                INSERT INTO omnix_trading_paper_balances (
                    workspace_id, account_id, currency, available
                ) VALUES (%s, %s, %s, %s)
                """,
                (self.context.workspace_id, account_id, currency, initial_cash),
            )
            ledger_id = f"reset:{account_id}:{expected_revision + 1}"
            uow.connection.execute(
                """
                INSERT INTO omnix_trading_paper_ledger (
                    workspace_id, account_id, ledger_id, entry_type,
                    currency, amount, idempotency_key, payload
                ) VALUES (%s, %s, %s, 'deposit', %s, %s, %s, %s::jsonb)
                """,
                (
                    self.context.workspace_id,
                    account_id,
                    ledger_id,
                    currency,
                    initial_cash,
                    ledger_id,
                    json.dumps({"source": "explicit_account_reset"}),
                ),
            )
            uow.connection.execute(
                """
                UPDATE omnix_trading_paper_accounts
                   SET enabled = TRUE, revision = revision + 1,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND account_id = %s
                """,
                (self.context.workspace_id, account_id),
            )
            uow.commit()
        return self.repository_factory().snapshot(account_id)

    def archive_account(
        self,
        account_id: str,
        *,
        expected_revision: int,
    ) -> PaperAccountSnapshot:
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                """
                UPDATE omnix_trading_paper_accounts
                   SET enabled = FALSE, revision = revision + 1,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND account_id = %s AND revision = %s
                RETURNING account_id
                """,
                (self.context.workspace_id, account_id, expected_revision),
            ).fetchone()
            if row is None:
                raise RevisionConflict(
                    f"Paper account expected revision {expected_revision}: {account_id}"
                )
            uow.connection.execute(
                """
                UPDATE omnix_trading_paper_orders
                   SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND account_id = %s AND status = 'open'
                """,
                (self.context.workspace_id, account_id),
            )
            uow.commit()
        return self.repository_factory().snapshot(account_id)


PaperLifecycleFactory = Callable[[], TradingPaperLifecycle]


def default_paper_lifecycle() -> TradingPaperLifecycle:
    return TradingPaperLifecycle()
