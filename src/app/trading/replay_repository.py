from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from app.persistence.tenant import TenantContext, local_tenant_context
from app.persistence.unit_of_work import PostgresUnitOfWork, unit_of_work

from .backtest import (
    BacktestEquityPoint,
    BacktestLogEntry,
    BacktestRunResult,
    BacktestTrade,
)
from .replay import FrozenDatasetSnapshot


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> AbstractContextManager[PostgresUnitOfWork]: ...


def _dataset(row) -> FrozenDatasetSnapshot:
    return FrozenDatasetSnapshot(
        dataset_id=str(row[0]),
        instrument_id=str(row[1]),
        requested_binding_id=str(row[2]) if row[2] is not None else None,
        resolved_binding_id=str(row[3]),
        provider=str(row[4]),
        interval=str(row[5]),
        adjustment_mode=str(row[6]),
        session_calendar=str(row[7]),
        exchange_timezone=str(row[8]),
        gap_policy=str(row[9]),
        dataset_fingerprint=str(row[10]),
        source_as_of=row[11],
        bars=tuple(row[12] or []),
        created_at=row[13],
    )


_DATASET_COLUMNS = """
    dataset_id, instrument_id, requested_binding_id, resolved_binding_id,
    provider, interval, adjustment_mode, session_calendar, exchange_timezone,
    gap_policy, dataset_fingerprint, source_as_of, bars, created_at
"""


class TradingReplayRepository:
    def __init__(
        self,
        *,
        context: TenantContext | None = None,
        uow_factory: UnitOfWorkFactory = unit_of_work,
    ) -> None:
        self.context = context or local_tenant_context()
        self.uow_factory = uow_factory

    def create_dataset(self, snapshot: FrozenDatasetSnapshot) -> FrozenDatasetSnapshot:
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                f"""
                INSERT INTO omnix_trading_datasets (
                    workspace_id, dataset_id, owner_user_id, instrument_id,
                    requested_binding_id, resolved_binding_id, provider, interval,
                    adjustment_mode, session_calendar, exchange_timezone, gap_policy,
                    dataset_fingerprint, source_as_of, bars, bar_count
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s::jsonb, %s
                )
                ON CONFLICT (workspace_id, dataset_fingerprint) DO UPDATE
                    SET dataset_id = omnix_trading_datasets.dataset_id
                RETURNING {_DATASET_COLUMNS}
                """,
                (
                    self.context.workspace_id,
                    snapshot.dataset_id,
                    self.context.user_id,
                    snapshot.instrument_id,
                    snapshot.requested_binding_id,
                    snapshot.resolved_binding_id,
                    snapshot.provider,
                    snapshot.interval,
                    snapshot.adjustment_mode,
                    snapshot.session_calendar,
                    snapshot.exchange_timezone,
                    snapshot.gap_policy,
                    snapshot.dataset_fingerprint,
                    snapshot.source_as_of,
                    json.dumps([bar.model_dump(mode="json") for bar in snapshot.bars]),
                    len(snapshot.bars),
                ),
            ).fetchone()
            uow.commit()
            return _dataset(row)

    def get_dataset(self, dataset_id: str) -> FrozenDatasetSnapshot | None:
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                f"SELECT {_DATASET_COLUMNS} FROM omnix_trading_datasets WHERE workspace_id = %s AND dataset_id = %s",
                (self.context.workspace_id, dataset_id),
            ).fetchone()
            return _dataset(row) if row else None

    def list_datasets(self, limit: int = 100) -> list[FrozenDatasetSnapshot]:
        with self.uow_factory() as uow:
            rows = uow.connection.execute(
                f"SELECT {_DATASET_COLUMNS} FROM omnix_trading_datasets WHERE workspace_id = %s ORDER BY created_at DESC LIMIT %s",
                (self.context.workspace_id, limit),
            ).fetchall()
            return [_dataset(row) for row in rows]

    def save_backtest(self, result: BacktestRunResult) -> BacktestRunResult:
        with self.uow_factory() as uow:
            uow.connection.execute(
                """
                INSERT INTO omnix_trading_backtest_runs (
                    workspace_id, run_id, dataset_id, strategy_id, strategy_parameters,
                    execution_policy, formula_version, status, initial_cash,
                    final_equity, total_return_percent, max_drawdown_percent,
                    trade_count, error_message, started_at, finished_at
                ) VALUES (
                    %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    self.context.workspace_id,
                    result.run_id,
                    result.dataset_id,
                    result.strategy_id,
                    json.dumps(result.strategy_parameters),
                    json.dumps(result.execution_policy),
                    result.formula_version,
                    result.status,
                    result.initial_cash,
                    result.final_equity,
                    result.total_return_percent,
                    result.max_drawdown_percent,
                    result.trade_count,
                    result.error_message,
                    result.started_at,
                    result.finished_at,
                ),
            )
            for trade in result.trades:
                uow.connection.execute(
                    """
                    INSERT INTO omnix_trading_backtest_trades (
                        workspace_id, run_id, trade_index, side,
                        signal_bar_index, fill_bar_index, signal_time,
                        fill_time, quantity, fill_price, commission, cash_after,
                        position_after
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        self.context.workspace_id,
                        result.run_id,
                        trade.trade_index,
                        trade.side,
                        trade.signal_bar_index,
                        trade.fill_bar_index,
                        trade.signal_time,
                        trade.fill_time,
                        trade.quantity,
                        trade.fill_price,
                        trade.commission,
                        trade.cash_after,
                        trade.position_after,
                    ),
                )
            for point in result.equity_curve:
                uow.connection.execute(
                    """
                    INSERT INTO omnix_trading_backtest_equity (
                        workspace_id, run_id, point_index, bar_time, cash,
                        position, equity, drawdown_percent
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        self.context.workspace_id,
                        result.run_id,
                        point.point_index,
                        point.bar_time,
                        point.cash,
                        point.position,
                        point.equity,
                        point.drawdown_percent,
                    ),
                )
            for entry in result.logs:
                uow.connection.execute(
                    """
                    INSERT INTO omnix_trading_backtest_logs (
                        workspace_id, run_id, log_index, bar_time, level,
                        message, payload
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        self.context.workspace_id,
                        result.run_id,
                        entry.log_index,
                        entry.bar_time,
                        entry.level,
                        entry.message,
                        json.dumps(entry.payload),
                    ),
                )
            uow.commit()
        return result

    def list_backtests(self, limit: int = 100) -> list[dict[str, object]]:
        with self.uow_factory() as uow:
            rows = uow.connection.execute(
                """
                SELECT run_id, dataset_id, strategy_id, status, initial_cash,
                       final_equity, total_return_percent, max_drawdown_percent,
                       trade_count, formula_version, started_at, finished_at,
                       error_message
                  FROM omnix_trading_backtest_runs
                 WHERE workspace_id = %s
                 ORDER BY created_at DESC
                 LIMIT %s
                """,
                (self.context.workspace_id, limit),
            ).fetchall()
            return [
                {
                    "run_id": str(row[0]),
                    "dataset_id": str(row[1]),
                    "strategy_id": str(row[2]),
                    "status": str(row[3]),
                    "initial_cash": str(row[4]),
                    "final_equity": str(row[5]),
                    "total_return_percent": str(row[6]),
                    "max_drawdown_percent": str(row[7]),
                    "trade_count": int(row[8]),
                    "formula_version": str(row[9]),
                    "started_at": row[10].isoformat(),
                    "finished_at": row[11].isoformat(),
                    "error_message": str(row[12]) if row[12] is not None else None,
                }
                for row in rows
            ]

    def get_backtest(self, run_id: str) -> BacktestRunResult | None:
        with self.uow_factory() as uow:
            run = uow.connection.execute(
                """
                SELECT dataset_id, strategy_id, strategy_parameters, execution_policy,
                       formula_version, status, initial_cash, final_equity,
                       total_return_percent, max_drawdown_percent, trade_count,
                       error_message, started_at, finished_at
                  FROM omnix_trading_backtest_runs
                 WHERE workspace_id = %s AND run_id = %s
                """,
                (self.context.workspace_id, run_id),
            ).fetchone()
            if run is None:
                return None
            dataset = self.get_dataset(str(run[0]))
            if dataset is None:
                return None
            trade_rows = uow.connection.execute(
                """
                SELECT trade_index, side, signal_bar_index, fill_bar_index,
                       signal_time, fill_time, quantity, fill_price,
                       commission, cash_after, position_after
                  FROM omnix_trading_backtest_trades
                 WHERE workspace_id = %s AND run_id = %s ORDER BY trade_index
                """,
                (self.context.workspace_id, run_id),
            ).fetchall()
            equity_rows = uow.connection.execute(
                """
                SELECT point_index, bar_time, cash, position, equity, drawdown_percent
                  FROM omnix_trading_backtest_equity
                 WHERE workspace_id = %s AND run_id = %s ORDER BY point_index
                """,
                (self.context.workspace_id, run_id),
            ).fetchall()
            log_rows = uow.connection.execute(
                """
                SELECT log_index, bar_time, level, message, payload
                  FROM omnix_trading_backtest_logs
                 WHERE workspace_id = %s AND run_id = %s ORDER BY log_index
                """,
                (self.context.workspace_id, run_id),
            ).fetchall()
            return BacktestRunResult(
                run_id=run_id,
                dataset_id=str(run[0]),
                dataset_fingerprint=dataset.dataset_fingerprint,
                strategy_id=str(run[1]),
                strategy_parameters=dict(run[2] or {}),
                execution_policy=dict(run[3] or {}),
                formula_version=str(run[4]),
                status=str(run[5]),
                initial_cash=Decimal(run[6]),
                final_equity=Decimal(run[7]),
                total_return_percent=Decimal(run[8]),
                max_drawdown_percent=Decimal(run[9]),
                trade_count=int(run[10]),
                error_message=str(run[11]) if run[11] is not None else None,
                started_at=run[12],
                finished_at=run[13],
                trades=tuple(
                    BacktestTrade(
                        trade_index=int(row[0]),
                        side=str(row[1]),
                        signal_bar_index=int(row[2]),
                        fill_bar_index=int(row[3]),
                        signal_time=row[4],
                        fill_time=row[5],
                        quantity=Decimal(row[6]),
                        fill_price=Decimal(row[7]),
                        commission=Decimal(row[8]),
                        cash_after=Decimal(row[9]),
                        position_after=Decimal(row[10]),
                    )
                    for row in trade_rows
                ),
                equity_curve=tuple(
                    BacktestEquityPoint(
                        point_index=int(row[0]),
                        bar_time=row[1],
                        cash=Decimal(row[2]),
                        position=Decimal(row[3]),
                        equity=Decimal(row[4]),
                        drawdown_percent=Decimal(row[5]),
                    )
                    for row in equity_rows
                ),
                logs=tuple(
                    BacktestLogEntry(
                        log_index=int(row[0]),
                        bar_time=row[1],
                        level=str(row[2]),
                        message=str(row[3]),
                        payload=dict(row[4] or {}),
                    )
                    for row in log_rows
                ),
            )


ReplayRepositoryFactory = Callable[[], TradingReplayRepository]


def default_replay_repository() -> TradingReplayRepository:
    return TradingReplayRepository()
