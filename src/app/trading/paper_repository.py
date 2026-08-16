from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from decimal import Decimal
from typing import Protocol

from app.persistence.tenant import TenantContext, local_tenant_context
from app.persistence.unit_of_work import PostgresUnitOfWork, unit_of_work

from .paper import (
    PaperAccount,
    PaperAccountCreate,
    PaperAccountSnapshot,
    PaperBalance,
    PaperFill,
    PaperLedgerEntry,
    PaperMarketObservation,
    PaperOrder,
    PaperOrderRequest,
    PaperPosition,
    paper_buy_reservation,
    paper_commission,
    paper_fill_decision,
    paper_fill_key,
    paper_order_request_matches,
    paper_realized_pnl,
    paper_unrealized_pnl,
)


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> AbstractContextManager[PostgresUnitOfWork]: ...


def _account(row) -> PaperAccount:
    return PaperAccount(
        account_id=str(row[0]),
        name=str(row[1]),
        base_currency=str(row[2]),
        commission_bps=Decimal(row[3]),
        enabled=bool(row[4]),
        revision=int(row[5]),
        created_at=row[6],
        updated_at=row[7],
    )


def _order(row) -> PaperOrder:
    return PaperOrder(
        account_id=str(row[0]),
        order_id=str(row[1]),
        instrument_id=str(row[2]),
        binding_id=str(row[3]) if row[3] is not None else None,
        side=str(row[4]),
        order_type=str(row[5]),
        quantity=Decimal(row[6]),
        limit_price=Decimal(row[7]) if row[7] is not None else None,
        stop_price=Decimal(row[8]) if row[8] is not None else None,
        reference_price=Decimal(row[9]) if row[9] is not None else None,
        status=str(row[10]),
        filled_quantity=Decimal(row[11]),
        average_fill_price=Decimal(row[12]) if row[12] is not None else None,
        idempotency_key=str(row[13]),
        rejection_reason=str(row[14]) if row[14] is not None else None,
        reserved_cash=Decimal(row[15]),
        created_at=row[16],
        updated_at=row[17],
    )


_ORDER_COLUMNS = """
    account_id, order_id, instrument_id, binding_id, side, order_type,
    quantity, limit_price, stop_price, reference_price, status,
    filled_quantity, average_fill_price, idempotency_key, rejection_reason,
    reserved_cash, created_at, updated_at
"""


class TradingPaperRepository:
    def __init__(
        self,
        *,
        context: TenantContext | None = None,
        uow_factory: UnitOfWorkFactory = unit_of_work,
    ) -> None:
        self.context = context or local_tenant_context()
        self.uow_factory = uow_factory

    def create_account(self, request: PaperAccountCreate) -> PaperAccountSnapshot:
        with self.uow_factory() as uow:
            account_row = uow.connection.execute(
                """
                INSERT INTO omnix_trading_paper_accounts (
                    workspace_id, account_id, owner_user_id, name,
                    base_currency, commission_bps
                ) VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING account_id, name, base_currency, commission_bps,
                          enabled, revision, created_at, updated_at
                """,
                (
                    self.context.workspace_id,
                    request.account_id,
                    self.context.user_id,
                    request.name,
                    request.base_currency,
                    request.commission_bps,
                ),
            ).fetchone()
            uow.connection.execute(
                """
                INSERT INTO omnix_trading_paper_balances (
                    workspace_id, account_id, currency, available
                ) VALUES (%s, %s, %s, %s)
                """,
                (
                    self.context.workspace_id,
                    request.account_id,
                    request.base_currency,
                    request.initial_cash,
                ),
            )
            ledger_id = f"deposit:{request.account_id}"
            uow.connection.execute(
                """
                INSERT INTO omnix_trading_paper_ledger (
                    workspace_id, account_id, ledger_id, entry_type, currency,
                    amount, idempotency_key, payload
                ) VALUES (%s, %s, %s, 'deposit', %s, %s, %s, %s::jsonb)
                """,
                (
                    self.context.workspace_id,
                    request.account_id,
                    ledger_id,
                    request.base_currency,
                    request.initial_cash,
                    ledger_id,
                    json.dumps({"source": "account_creation"}),
                ),
            )
            uow.commit()
        return self.snapshot(request.account_id, account=_account(account_row))

    def list_accounts(self, limit: int = 100) -> list[PaperAccount]:
        with self.uow_factory() as uow:
            rows = uow.connection.execute(
                """
                SELECT account_id, name, base_currency, commission_bps,
                       enabled, revision, created_at, updated_at
                  FROM omnix_trading_paper_accounts
                 WHERE workspace_id = %s
                 ORDER BY created_at DESC LIMIT %s
                """,
                (self.context.workspace_id, limit),
            ).fetchall()
            return [_account(row) for row in rows]

    def place_order(
        self,
        account_id: str,
        request: PaperOrderRequest,
    ) -> PaperOrder:
        with self.uow_factory() as uow:
            account_row = uow.connection.execute(
                """
                SELECT account_id, name, base_currency, commission_bps,
                       enabled, revision, created_at, updated_at
                  FROM omnix_trading_paper_accounts
                 WHERE workspace_id = %s AND account_id = %s
                 FOR UPDATE
                """,
                (self.context.workspace_id, account_id),
            ).fetchone()
            if account_row is None:
                raise ValueError(f"paper_account_not_found: {account_id}")
            account = _account(account_row)
            if not account.enabled:
                raise ValueError(f"paper_account_disabled: {account_id}")

            existing_row = uow.connection.execute(
                f"""
                SELECT {_ORDER_COLUMNS}
                  FROM omnix_trading_paper_orders
                 WHERE workspace_id = %s AND account_id = %s AND idempotency_key = %s
                 FOR UPDATE
                """,
                (self.context.workspace_id, account_id, request.idempotency_key),
            ).fetchone()
            if existing_row is not None:
                existing = _order(existing_row)
                if not paper_order_request_matches(existing, request):
                    raise ValueError("paper_idempotency_payload_mismatch")
                return existing

            reserved_cash = Decimal("0")
            if request.side == "buy":
                balance_row = uow.connection.execute(
                    """
                    SELECT available, reserved
                      FROM omnix_trading_paper_balances
                     WHERE workspace_id = %s AND account_id = %s AND currency = %s
                     FOR UPDATE
                    """,
                    (self.context.workspace_id, account_id, account.base_currency),
                ).fetchone()
                available = Decimal(balance_row[0]) if balance_row else Decimal("0")
                reserved_cash = paper_buy_reservation(
                    request,
                    available_cash=available,
                    commission_bps=account.commission_bps,
                )
                if reserved_cash <= 0 or available < reserved_cash:
                    raise ValueError("insufficient_paper_cash")
                uow.connection.execute(
                    """
                    UPDATE omnix_trading_paper_balances
                       SET available = available - %s,
                           reserved = reserved + %s,
                           updated_at = CURRENT_TIMESTAMP
                     WHERE workspace_id = %s AND account_id = %s AND currency = %s
                    """,
                    (
                        reserved_cash,
                        reserved_cash,
                        self.context.workspace_id,
                        account_id,
                        account.base_currency,
                    ),
                )
            else:
                position_row = uow.connection.execute(
                    """
                    SELECT quantity, reserved_quantity
                      FROM omnix_trading_paper_positions
                     WHERE workspace_id = %s AND account_id = %s AND instrument_id = %s
                     FOR UPDATE
                    """,
                    (self.context.workspace_id, account_id, request.instrument_id),
                ).fetchone()
                quantity = Decimal(position_row[0]) if position_row else Decimal("0")
                already_reserved = Decimal(position_row[1]) if position_row else Decimal("0")
                if quantity - already_reserved < request.quantity:
                    raise ValueError("insufficient_paper_position")
                uow.connection.execute(
                    """
                    UPDATE omnix_trading_paper_positions
                       SET reserved_quantity = reserved_quantity + %s,
                           updated_at = CURRENT_TIMESTAMP
                     WHERE workspace_id = %s AND account_id = %s AND instrument_id = %s
                    """,
                    (
                        request.quantity,
                        self.context.workspace_id,
                        account_id,
                        request.instrument_id,
                    ),
                )

            row = uow.connection.execute(
                f"""
                INSERT INTO omnix_trading_paper_orders (
                    workspace_id, account_id, order_id, instrument_id, binding_id,
                    side, order_type, quantity, limit_price, stop_price,
                    reference_price, status, idempotency_key, reserved_cash
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'open', %s, %s)
                RETURNING {_ORDER_COLUMNS}
                """,
                (
                    self.context.workspace_id,
                    account_id,
                    request.order_id,
                    request.instrument_id,
                    request.binding_id,
                    request.side,
                    request.order_type,
                    request.quantity,
                    request.limit_price,
                    request.stop_price,
                    request.reference_price,
                    request.idempotency_key,
                    reserved_cash,
                ),
            ).fetchone()
            uow.commit()
            return _order(row)

    def cancel_order(self, account_id: str, order_id: str) -> PaperOrder:
        with self.uow_factory() as uow:
            account_row = uow.connection.execute(
                """
                SELECT account_id, name, base_currency, commission_bps,
                       enabled, revision, created_at, updated_at
                  FROM omnix_trading_paper_accounts
                 WHERE workspace_id = %s AND account_id = %s
                 FOR UPDATE
                """,
                (self.context.workspace_id, account_id),
            ).fetchone()
            if account_row is None:
                raise ValueError(f"paper_account_not_found: {account_id}")
            account = _account(account_row)
            order_row = uow.connection.execute(
                f"""
                SELECT {_ORDER_COLUMNS}
                  FROM omnix_trading_paper_orders
                 WHERE workspace_id = %s AND account_id = %s AND order_id = %s
                   AND status = 'open'
                 FOR UPDATE
                """,
                (self.context.workspace_id, account_id, order_id),
            ).fetchone()
            if order_row is None:
                raise ValueError("paper_order_not_open")
            order = _order(order_row)
            self._release_order_reservation(uow, account, order)
            row = uow.connection.execute(
                f"""
                UPDATE omnix_trading_paper_orders
                   SET status = 'cancelled', reserved_cash = 0,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND account_id = %s AND order_id = %s
                RETURNING {_ORDER_COLUMNS}
                """,
                (self.context.workspace_id, account_id, order_id),
            ).fetchone()
            uow.commit()
            return _order(row)

    def _release_order_reservation(
        self,
        uow: PostgresUnitOfWork,
        account: PaperAccount,
        order: PaperOrder,
    ) -> None:
        if order.side == "buy" and order.reserved_cash > 0:
            uow.connection.execute(
                """
                UPDATE omnix_trading_paper_balances
                   SET available = available + %s,
                       reserved = reserved - %s,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND account_id = %s AND currency = %s
                """,
                (
                    order.reserved_cash,
                    order.reserved_cash,
                    self.context.workspace_id,
                    account.account_id,
                    account.base_currency,
                ),
            )
        elif order.side == "sell":
            uow.connection.execute(
                """
                UPDATE omnix_trading_paper_positions
                   SET reserved_quantity = reserved_quantity - %s,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND account_id = %s AND instrument_id = %s
                   AND reserved_quantity >= %s
                """,
                (
                    order.quantity,
                    self.context.workspace_id,
                    account.account_id,
                    order.instrument_id,
                    order.quantity,
                ),
            )

    def process_observation(
        self,
        account_id: str,
        observation: PaperMarketObservation,
    ) -> list[PaperFill]:
        fills: list[PaperFill] = []
        with self.uow_factory() as uow:
            account_row = uow.connection.execute(
                """
                SELECT account_id, name, base_currency, commission_bps,
                       enabled, revision, created_at, updated_at
                  FROM omnix_trading_paper_accounts
                 WHERE workspace_id = %s AND account_id = %s
                 FOR UPDATE
                """,
                (self.context.workspace_id, account_id),
            ).fetchone()
            if account_row is None:
                raise ValueError(f"paper_account_not_found: {account_id}")
            account = _account(account_row)
            balance_row = uow.connection.execute(
                """
                SELECT available, reserved
                  FROM omnix_trading_paper_balances
                 WHERE workspace_id = %s AND account_id = %s AND currency = %s
                 FOR UPDATE
                """,
                (self.context.workspace_id, account_id, account.base_currency),
            ).fetchone()
            cash_available = Decimal(balance_row[0]) if balance_row else Decimal("0")
            cash_reserved = Decimal(balance_row[1]) if balance_row else Decimal("0")
            position_row = uow.connection.execute(
                """
                SELECT quantity, reserved_quantity, average_cost, realized_pnl
                  FROM omnix_trading_paper_positions
                 WHERE workspace_id = %s AND account_id = %s AND instrument_id = %s
                 FOR UPDATE
                """,
                (self.context.workspace_id, account_id, observation.instrument_id),
            ).fetchone()
            position_quantity = Decimal(position_row[0]) if position_row else Decimal("0")
            reserved_quantity = Decimal(position_row[1]) if position_row else Decimal("0")
            average_cost = Decimal(position_row[2]) if position_row else Decimal("0")
            realized_pnl = Decimal(position_row[3]) if position_row else Decimal("0")
            order_rows = uow.connection.execute(
                f"""
                SELECT {_ORDER_COLUMNS}
                  FROM omnix_trading_paper_orders
                 WHERE workspace_id = %s AND account_id = %s
                   AND instrument_id = %s AND status = 'open'
                 ORDER BY created_at, order_id
                 FOR UPDATE
                """,
                (self.context.workspace_id, account_id, observation.instrument_id),
            ).fetchall()

            for row in order_rows:
                order = _order(row)
                decision = paper_fill_decision(order, observation)
                if not decision.should_fill or decision.fill_price is None:
                    continue
                notional = order.quantity * decision.fill_price
                commission = paper_commission(notional, account.commission_bps)
                total_cost = notional + commission
                rejection = None
                if order.side == "buy" and order.reserved_cash < total_cost:
                    rejection = "insufficient_paper_cash"
                if order.side == "sell" and (
                    position_quantity < order.quantity or reserved_quantity < order.quantity
                ):
                    rejection = "insufficient_paper_position"
                if rejection:
                    if order.side == "buy":
                        cash_available += order.reserved_cash
                        cash_reserved -= order.reserved_cash
                    else:
                        release_quantity = min(reserved_quantity, order.quantity)
                        reserved_quantity -= release_quantity
                    uow.connection.execute(
                        """
                        UPDATE omnix_trading_paper_orders
                           SET status = 'rejected', rejection_reason = %s,
                               reserved_cash = 0, updated_at = CURRENT_TIMESTAMP
                         WHERE workspace_id = %s AND account_id = %s AND order_id = %s
                        """,
                        (rejection, self.context.workspace_id, account_id, order.order_id),
                    )
                    continue

                key = paper_fill_key(account_id, order.order_id, observation)
                fill_id = key[:32]
                inserted = uow.connection.execute(
                    """
                    INSERT INTO omnix_trading_paper_fills (
                        workspace_id, account_id, fill_id, order_id, instrument_id,
                        side, quantity, price, commission, source_time,
                        evaluated_at, idempotency_key
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (workspace_id, account_id, idempotency_key) DO NOTHING
                    RETURNING fill_id
                    """,
                    (
                        self.context.workspace_id,
                        account_id,
                        fill_id,
                        order.order_id,
                        order.instrument_id,
                        order.side,
                        order.quantity,
                        decision.fill_price,
                        commission,
                        observation.source_time,
                        observation.evaluated_at,
                        key,
                    ),
                ).fetchone()
                if inserted is None:
                    continue

                if order.side == "buy":
                    prior_cost = position_quantity * average_cost
                    cash_reserved -= order.reserved_cash
                    cash_available += order.reserved_cash - total_cost
                    position_quantity += order.quantity
                    average_cost = (prior_cost + notional) / position_quantity
                    realized_delta = Decimal("0")
                else:
                    reserved_quantity -= order.quantity
                    cash_available += notional - commission
                    realized_delta = paper_realized_pnl(
                        order.quantity,
                        average_cost,
                        decision.fill_price,
                    )
                    realized_pnl += realized_delta
                    position_quantity -= order.quantity
                    if position_quantity == 0:
                        average_cost = Decimal("0")

                uow.connection.execute(
                    """
                    UPDATE omnix_trading_paper_balances
                       SET available = %s, reserved = %s, updated_at = CURRENT_TIMESTAMP
                     WHERE workspace_id = %s AND account_id = %s AND currency = %s
                    """,
                    (
                        cash_available,
                        cash_reserved,
                        self.context.workspace_id,
                        account_id,
                        account.base_currency,
                    ),
                )
                unrealized = paper_unrealized_pnl(
                    position_quantity,
                    average_cost,
                    observation.price,
                )
                uow.connection.execute(
                    """
                    INSERT INTO omnix_trading_paper_positions (
                        workspace_id, account_id, instrument_id, quantity,
                        reserved_quantity, average_cost, realized_pnl,
                        last_price, unrealized_pnl
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (workspace_id, account_id, instrument_id) DO UPDATE
                       SET quantity = EXCLUDED.quantity,
                           reserved_quantity = EXCLUDED.reserved_quantity,
                           average_cost = EXCLUDED.average_cost,
                           realized_pnl = EXCLUDED.realized_pnl,
                           last_price = EXCLUDED.last_price,
                           unrealized_pnl = EXCLUDED.unrealized_pnl,
                           updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        self.context.workspace_id,
                        account_id,
                        order.instrument_id,
                        position_quantity,
                        reserved_quantity,
                        average_cost,
                        realized_pnl,
                        observation.price,
                        unrealized,
                    ),
                )
                uow.connection.execute(
                    """
                    UPDATE omnix_trading_paper_orders
                       SET status = 'filled', filled_quantity = quantity,
                           average_fill_price = %s, reserved_cash = 0,
                           updated_at = CURRENT_TIMESTAMP
                     WHERE workspace_id = %s AND account_id = %s AND order_id = %s
                    """,
                    (decision.fill_price, self.context.workspace_id, account_id, order.order_id),
                )

                ledger_rows = [
                    ("trade_cash", notional if order.side == "sell" else -notional),
                    ("commission", -commission),
                ]
                if realized_delta != 0:
                    ledger_rows.append(("realized_pnl", realized_delta))
                for entry_type, amount in ledger_rows:
                    ledger_key = f"{key}:{entry_type}"
                    uow.connection.execute(
                        """
                        INSERT INTO omnix_trading_paper_ledger (
                            workspace_id, account_id, ledger_id, entry_type,
                            currency, amount, order_id, fill_id,
                            idempotency_key, payload
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                        ON CONFLICT (workspace_id, account_id, idempotency_key) DO NOTHING
                        """,
                        (
                            self.context.workspace_id,
                            account_id,
                            ledger_key[:64],
                            entry_type,
                            account.base_currency,
                            amount,
                            order.order_id,
                            fill_id,
                            ledger_key,
                            json.dumps(
                                {
                                    "provider": observation.provider,
                                    "binding_id": observation.binding_id,
                                    "source_time": observation.source_time.isoformat(),
                                    "high": str(observation.high) if observation.high is not None else None,
                                    "low": str(observation.low) if observation.low is not None else None,
                                }
                            ),
                        ),
                    )
                fills.append(
                    PaperFill(
                        fill_id=fill_id,
                        order_id=order.order_id,
                        instrument_id=order.instrument_id,
                        side=order.side,
                        quantity=order.quantity,
                        price=decision.fill_price,
                        commission=commission,
                        source_time=observation.source_time,
                        evaluated_at=observation.evaluated_at,
                        idempotency_key=key,
                    )
                )

            if position_row is not None and not fills:
                unrealized = paper_unrealized_pnl(
                    position_quantity,
                    average_cost,
                    observation.price,
                )
                uow.connection.execute(
                    """
                    UPDATE omnix_trading_paper_positions
                       SET last_price = %s, unrealized_pnl = %s,
                           reserved_quantity = %s, updated_at = CURRENT_TIMESTAMP
                     WHERE workspace_id = %s AND account_id = %s AND instrument_id = %s
                    """,
                    (
                        observation.price,
                        unrealized,
                        reserved_quantity,
                        self.context.workspace_id,
                        account_id,
                        observation.instrument_id,
                    ),
                )
            if balance_row is not None and not fills:
                uow.connection.execute(
                    """
                    UPDATE omnix_trading_paper_balances
                       SET available = %s, reserved = %s, updated_at = CURRENT_TIMESTAMP
                     WHERE workspace_id = %s AND account_id = %s AND currency = %s
                    """,
                    (
                        cash_available,
                        cash_reserved,
                        self.context.workspace_id,
                        account_id,
                        account.base_currency,
                    ),
                )
            uow.commit()
        return fills

    def snapshot(
        self,
        account_id: str,
        *,
        account: PaperAccount | None = None,
    ) -> PaperAccountSnapshot:
        with self.uow_factory() as uow:
            if account is None:
                row = uow.connection.execute(
                    """
                    SELECT account_id, name, base_currency, commission_bps,
                           enabled, revision, created_at, updated_at
                      FROM omnix_trading_paper_accounts
                     WHERE workspace_id = %s AND account_id = %s
                    """,
                    (self.context.workspace_id, account_id),
                ).fetchone()
                if row is None:
                    raise ValueError(f"paper_account_not_found: {account_id}")
                account = _account(row)
            balances = [
                PaperBalance(
                    currency=str(row[0]),
                    available=Decimal(row[1]),
                    reserved=Decimal(row[2]),
                )
                for row in uow.connection.execute(
                    "SELECT currency, available, reserved FROM omnix_trading_paper_balances WHERE workspace_id = %s AND account_id = %s ORDER BY currency",
                    (self.context.workspace_id, account_id),
                ).fetchall()
            ]
            positions = [
                PaperPosition(
                    instrument_id=str(row[0]),
                    quantity=Decimal(row[1]),
                    reserved_quantity=Decimal(row[2]),
                    average_cost=Decimal(row[3]),
                    realized_pnl=Decimal(row[4]),
                    last_price=Decimal(row[5]) if row[5] is not None else None,
                    unrealized_pnl=Decimal(row[6]),
                )
                for row in uow.connection.execute(
                    "SELECT instrument_id, quantity, reserved_quantity, average_cost, realized_pnl, last_price, unrealized_pnl FROM omnix_trading_paper_positions WHERE workspace_id = %s AND account_id = %s ORDER BY instrument_id",
                    (self.context.workspace_id, account_id),
                ).fetchall()
            ]
            orders = [
                _order(row)
                for row in uow.connection.execute(
                    f"SELECT {_ORDER_COLUMNS} FROM omnix_trading_paper_orders WHERE workspace_id = %s AND account_id = %s AND status = 'open' ORDER BY created_at",
                    (self.context.workspace_id, account_id),
                ).fetchall()
            ]
            order_history = [
                _order(row)
                for row in uow.connection.execute(
                    f"SELECT {_ORDER_COLUMNS} FROM omnix_trading_paper_orders WHERE workspace_id = %s AND account_id = %s ORDER BY created_at DESC, order_id DESC LIMIT 200",
                    (self.context.workspace_id, account_id),
                ).fetchall()
            ]
            fills = [
                PaperFill(
                    fill_id=str(row[0]),
                    order_id=str(row[1]),
                    instrument_id=str(row[2]),
                    side=str(row[3]),
                    quantity=Decimal(row[4]),
                    price=Decimal(row[5]),
                    commission=Decimal(row[6]),
                    source_time=row[7],
                    evaluated_at=row[8],
                    idempotency_key=str(row[9]),
                )
                for row in uow.connection.execute(
                    "SELECT fill_id, order_id, instrument_id, side, quantity, price, commission, source_time, evaluated_at, idempotency_key FROM omnix_trading_paper_fills WHERE workspace_id = %s AND account_id = %s ORDER BY created_at DESC LIMIT 100",
                    (self.context.workspace_id, account_id),
                ).fetchall()
            ]
            ledger = [
                PaperLedgerEntry(
                    ledger_id=str(row[0]),
                    entry_type=str(row[1]),
                    currency=str(row[2]),
                    amount=Decimal(row[3]),
                    order_id=str(row[4]) if row[4] else None,
                    fill_id=str(row[5]) if row[5] else None,
                    idempotency_key=str(row[6]),
                    payload=dict(row[7] or {}),
                    created_at=row[8],
                )
                for row in uow.connection.execute(
                    "SELECT ledger_id, entry_type, currency, amount, order_id, fill_id, idempotency_key, payload, created_at FROM omnix_trading_paper_ledger WHERE workspace_id = %s AND account_id = %s ORDER BY created_at DESC LIMIT 200",
                    (self.context.workspace_id, account_id),
                ).fetchall()
            ]
            return PaperAccountSnapshot(
                account=account,
                balances=balances,
                positions=positions,
                open_orders=orders,
                order_history=order_history,
                recent_fills=fills,
                recent_ledger=ledger,
            )


PaperRepositoryFactory = Callable[[], TradingPaperRepository]


def default_paper_repository() -> TradingPaperRepository:
    return TradingPaperRepository()
