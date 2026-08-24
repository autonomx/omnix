from __future__ import annotations

from decimal import Decimal

from app.persistence.tenant import TenantContext, local_tenant_context
from app.persistence.unit_of_work import unit_of_work

from .paper_protection import PaperPositionProtection, PaperProtectionStatus, PaperProtectionUpsert


_COLUMNS = """
    account_id, instrument_id, binding_id, entry_order_id, exit_order_id,
    take_profit, stop_loss, status, trigger_reason, revision, created_at, updated_at
"""


def _protection(row) -> PaperPositionProtection:
    return PaperPositionProtection(
        account_id=str(row[0]),
        instrument_id=str(row[1]),
        binding_id=str(row[2]) if row[2] is not None else None,
        entry_order_id=str(row[3]) if row[3] is not None else None,
        exit_order_id=str(row[4]) if row[4] is not None else None,
        take_profit=Decimal(row[5]) if row[5] is not None else None,
        stop_loss=Decimal(row[6]) if row[6] is not None else None,
        status=str(row[7]),
        trigger_reason=str(row[8]) if row[8] is not None else None,
        revision=int(row[9]),
        created_at=row[10],
        updated_at=row[11],
    )


class TradingPaperProtectionRepository:
    def __init__(self, *, context: TenantContext | None = None, uow_factory=unit_of_work) -> None:
        self.context = context or local_tenant_context()
        self.uow_factory = uow_factory

    def list(
        self,
        account_id: str,
        *,
        active_only: bool = True,
    ) -> list[PaperPositionProtection]:
        where = "AND status IN ('pending_entry', 'active', 'exit_submitted')" if active_only else ""
        with self.uow_factory() as uow:
            account = uow.connection.execute(
                "SELECT 1 FROM omnix_trading_paper_accounts WHERE workspace_id = %s AND account_id = %s",
                (self.context.workspace_id, account_id),
            ).fetchone()
            if account is None:
                raise ValueError(f"paper_account_not_found: {account_id}")
            rows = uow.connection.execute(
                f"""
                SELECT {_COLUMNS}
                  FROM omnix_trading_paper_protections
                 WHERE workspace_id = %s AND account_id = %s {where}
                 ORDER BY updated_at DESC, instrument_id
                """,
                (self.context.workspace_id, account_id),
            ).fetchall()
        return [_protection(row) for row in rows]

    def get(
        self,
        account_id: str,
        instrument_id: str,
        *,
        include_inactive: bool = True,
    ) -> PaperPositionProtection:
        suffix = "" if include_inactive else "AND status IN ('pending_entry', 'active', 'exit_submitted')"
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                f"""
                SELECT {_COLUMNS}
                  FROM omnix_trading_paper_protections
                 WHERE workspace_id = %s AND account_id = %s AND instrument_id = %s {suffix}
                """,
                (self.context.workspace_id, account_id, instrument_id),
            ).fetchone()
        if row is None:
            raise ValueError("paper_protection_not_found")
        return _protection(row)

    def arm_pending_entry(
        self,
        account_id: str,
        request: PaperProtectionUpsert,
    ) -> PaperPositionProtection:
        """Persist protection intent before the corresponding entry can execute.

        The entry order is deliberately allowed to be absent at this point. The
        paper monitor treats such a pending row as inert until the server order
        exists, which removes the fill-before-protection race while remaining
        fail-closed if the process stops between the two writes.
        """
        if not request.entry_order_id:
            raise ValueError("paper_protection_pending_entry_requires_order_id")
        with self.uow_factory() as uow:
            account = uow.connection.execute(
                """
                SELECT enabled
                  FROM omnix_trading_paper_accounts
                 WHERE workspace_id = %s AND account_id = %s
                 FOR UPDATE
                """,
                (self.context.workspace_id, account_id),
            ).fetchone()
            if account is None:
                raise ValueError(f"paper_account_not_found: {account_id}")
            if not bool(account[0]):
                raise ValueError(f"paper_account_disabled: {account_id}")

            existing = uow.connection.execute(
                f"""
                SELECT {_COLUMNS}
                  FROM omnix_trading_paper_protections
                 WHERE workspace_id = %s AND account_id = %s AND instrument_id = %s
                 FOR UPDATE
                """,
                (self.context.workspace_id, account_id, request.instrument_id),
            ).fetchone()
            if existing is not None and str(existing[7]) == "exit_submitted":
                raise ValueError("paper_protection_exit_already_submitted")

            row = uow.connection.execute(
                f"""
                INSERT INTO omnix_trading_paper_protections (
                    workspace_id, account_id, instrument_id, binding_id,
                    entry_order_id, take_profit, stop_loss, status,
                    exit_order_id, trigger_reason
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending_entry', NULL, 'entry_armed')
                ON CONFLICT (workspace_id, account_id, instrument_id) DO UPDATE
                   SET binding_id = EXCLUDED.binding_id,
                       entry_order_id = EXCLUDED.entry_order_id,
                       take_profit = EXCLUDED.take_profit,
                       stop_loss = EXCLUDED.stop_loss,
                       status = 'pending_entry',
                       exit_order_id = NULL,
                       trigger_reason = 'entry_armed',
                       revision = omnix_trading_paper_protections.revision + 1,
                       updated_at = CURRENT_TIMESTAMP
                RETURNING {_COLUMNS}
                """,
                (
                    self.context.workspace_id,
                    account_id,
                    request.instrument_id,
                    request.binding_id,
                    request.entry_order_id,
                    request.take_profit,
                    request.stop_loss,
                ),
            ).fetchone()
            uow.commit()
        return _protection(row)

    def upsert(
        self,
        account_id: str,
        request: PaperProtectionUpsert,
    ) -> PaperPositionProtection:
        with self.uow_factory() as uow:
            account = uow.connection.execute(
                """
                SELECT enabled
                  FROM omnix_trading_paper_accounts
                 WHERE workspace_id = %s AND account_id = %s
                 FOR UPDATE
                """,
                (self.context.workspace_id, account_id),
            ).fetchone()
            if account is None:
                raise ValueError(f"paper_account_not_found: {account_id}")
            if not bool(account[0]):
                raise ValueError(f"paper_account_disabled: {account_id}")

            existing = uow.connection.execute(
                f"""
                SELECT {_COLUMNS}
                  FROM omnix_trading_paper_protections
                 WHERE workspace_id = %s AND account_id = %s AND instrument_id = %s
                 FOR UPDATE
                """,
                (self.context.workspace_id, account_id, request.instrument_id),
            ).fetchone()
            if existing is not None and str(existing[7]) == "exit_submitted":
                raise ValueError("paper_protection_exit_already_submitted")

            position = uow.connection.execute(
                """
                SELECT quantity
                  FROM omnix_trading_paper_positions
                 WHERE workspace_id = %s AND account_id = %s AND instrument_id = %s
                """,
                (self.context.workspace_id, account_id, request.instrument_id),
            ).fetchone()
            has_position = position is not None and Decimal(position[0]) != 0

            entry_order_id = request.entry_order_id
            binding_id = request.binding_id
            entry = None
            if entry_order_id:
                entry = uow.connection.execute(
                    """
                    SELECT status, instrument_id, binding_id
                      FROM omnix_trading_paper_orders
                     WHERE workspace_id = %s AND account_id = %s AND order_id = %s
                    """,
                    (self.context.workspace_id, account_id, entry_order_id),
                ).fetchone()
                if entry is None:
                    raise ValueError("paper_protection_entry_order_not_found")
                if str(entry[1]) != request.instrument_id:
                    raise ValueError("paper_protection_entry_order_instrument_mismatch")
            elif not has_position:
                # The current UI can attach protection immediately after placing
                # an order. Infer that newest still-open entry so browser state is
                # never required for authority or recovery after a reload.
                entry = uow.connection.execute(
                    """
                    SELECT status, instrument_id, binding_id, order_id
                      FROM omnix_trading_paper_orders
                     WHERE workspace_id = %s AND account_id = %s
                       AND instrument_id = %s AND status = 'open'
                     ORDER BY created_at DESC, order_id DESC
                     LIMIT 1
                    """,
                    (self.context.workspace_id, account_id, request.instrument_id),
                ).fetchone()
                if entry is not None:
                    entry_order_id = str(entry[3])
            has_entry_order = entry is not None and str(entry[0]) in {"open", "filled"}
            if binding_id is None and entry is not None and entry[2] is not None:
                binding_id = str(entry[2])
            if not has_position and not has_entry_order:
                raise ValueError("paper_protection_requires_position_or_entry_order")

            status = "active" if has_position else "pending_entry"
            row = uow.connection.execute(
                f"""
                INSERT INTO omnix_trading_paper_protections (
                    workspace_id, account_id, instrument_id, binding_id,
                    entry_order_id, take_profit, stop_loss, status,
                    exit_order_id, trigger_reason
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL)
                ON CONFLICT (workspace_id, account_id, instrument_id) DO UPDATE
                   SET binding_id = EXCLUDED.binding_id,
                       entry_order_id = EXCLUDED.entry_order_id,
                       take_profit = EXCLUDED.take_profit,
                       stop_loss = EXCLUDED.stop_loss,
                       status = EXCLUDED.status,
                       exit_order_id = NULL,
                       trigger_reason = NULL,
                       revision = omnix_trading_paper_protections.revision + 1,
                       updated_at = CURRENT_TIMESTAMP
                RETURNING {_COLUMNS}
                """,
                (
                    self.context.workspace_id,
                    account_id,
                    request.instrument_id,
                    binding_id,
                    entry_order_id,
                    request.take_profit,
                    request.stop_loss,
                    status,
                ),
            ).fetchone()
            uow.commit()
        return _protection(row)

    def clear(self, account_id: str, instrument_id: str) -> PaperPositionProtection:
        return self.transition(
            account_id,
            instrument_id,
            status="cancelled",
            exit_order_id=None,
            trigger_reason="user_cleared",
        )

    def transition(
        self,
        account_id: str,
        instrument_id: str,
        *,
        status: PaperProtectionStatus,
        exit_order_id: str | None,
        trigger_reason: str | None,
        expected_revision: int | None = None,
    ) -> PaperPositionProtection:
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                f"""
                SELECT {_COLUMNS}
                  FROM omnix_trading_paper_protections
                 WHERE workspace_id = %s AND account_id = %s AND instrument_id = %s
                 FOR UPDATE
                """,
                (self.context.workspace_id, account_id, instrument_id),
            ).fetchone()
            if row is None:
                raise ValueError("paper_protection_not_found")
            current = _protection(row)
            if expected_revision is not None and current.revision != expected_revision:
                raise ValueError("paper_protection_revision_conflict")
            updated = uow.connection.execute(
                f"""
                UPDATE omnix_trading_paper_protections
                   SET status = %s,
                       exit_order_id = %s,
                       trigger_reason = %s,
                       revision = revision + 1,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND account_id = %s AND instrument_id = %s
                RETURNING {_COLUMNS}
                """,
                (
                    status,
                    exit_order_id,
                    trigger_reason,
                    self.context.workspace_id,
                    account_id,
                    instrument_id,
                ),
            ).fetchone()
            uow.commit()
        return _protection(updated)


def default_paper_protection_repository() -> TradingPaperProtectionRepository:
    return TradingPaperProtectionRepository()
