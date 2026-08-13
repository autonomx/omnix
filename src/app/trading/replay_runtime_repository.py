from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Any

from app.persistence.blob_store import LocalBlobStore

from .backtest import (
    BacktestArtifactReference,
    BacktestEquityPoint,
    BacktestLogEntry,
    BacktestRunResult,
    BacktestTrade,
)
from .replay_repository import TradingReplayRepository


class TradingReplayRuntimeRepository(TradingReplayRepository):
    def __init__(self, *args, blob_store: LocalBlobStore | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.blob_store = blob_store or LocalBlobStore()

    def _artifact_key(self, run_id: str) -> str:
        workspace = hashlib.sha256(
            self.context.workspace_id.encode("utf-8")
        ).hexdigest()[:16]
        safe_run = hashlib.sha256(run_id.encode("utf-8")).hexdigest()
        return f"trading/backtests/{workspace}/{safe_run}.json"

    def save_backtest(self, result: BacktestRunResult) -> BacktestRunResult:
        storage_key = self._artifact_key(result.run_id)
        blob = self.blob_store.put_bytes(
            storage_key,
            result.model_dump_json(indent=2).encode("utf-8"),
        )
        artifact = BacktestArtifactReference(
            storage_provider=str(blob["storage_provider"]),
            storage_key=str(blob["storage_key"]),
            checksum_sha256=str(blob["checksum_sha256"]),
            byte_size=int(blob["byte_size"]),
        )
        saved = result.model_copy(update={"artifact": artifact})
        try:
            super().save_backtest(saved)
            with self.uow_factory() as uow:
                uow.connection.execute(
                    """
                    UPDATE omnix_trading_backtest_runs
                       SET win_rate_percent = %s,
                           exposure_percent = %s,
                           artifact_storage_provider = %s,
                           artifact_storage_key = %s,
                           artifact_checksum_sha256 = %s,
                           artifact_byte_size = %s
                     WHERE workspace_id = %s AND run_id = %s
                    """,
                    (
                        saved.win_rate_percent,
                        saved.exposure_percent,
                        artifact.storage_provider,
                        artifact.storage_key,
                        artifact.checksum_sha256,
                        artifact.byte_size,
                        self.context.workspace_id,
                        saved.run_id,
                    ),
                )
                uow.commit()
        except Exception:
            if bool(blob.get("created")):
                self.blob_store.delete(storage_key)
            raise
        return saved

    def list_backtests(self, limit: int = 100) -> list[dict[str, object]]:
        base = super().list_backtests(limit)
        if not base:
            return base
        run_ids = [str(item["run_id"]) for item in base]
        with self.uow_factory() as uow:
            rows = uow.connection.execute(
                """
                SELECT run_id, win_rate_percent, exposure_percent,
                       artifact_storage_provider, artifact_storage_key,
                       artifact_checksum_sha256, artifact_byte_size
                  FROM omnix_trading_backtest_runs
                 WHERE workspace_id = %s AND run_id = ANY(%s)
                """,
                (self.context.workspace_id, run_ids),
            ).fetchall()
        metadata = {str(row[0]): row for row in rows}
        for item in base:
            row = metadata.get(str(item["run_id"]))
            if row is None:
                continue
            item["win_rate_percent"] = str(row[1])
            item["exposure_percent"] = str(row[2])
            item["artifact"] = self._artifact_from_row(row[3:])
        return base

    @staticmethod
    def _artifact_from_row(row) -> dict[str, object] | None:
        if not row or row[0] is None:
            return None
        return {
            "storage_provider": str(row[0]),
            "storage_key": str(row[1]),
            "checksum_sha256": str(row[2]),
            "byte_size": int(row[3]),
        }

    def get_backtest(self, run_id: str) -> BacktestRunResult | None:
        with self.uow_factory() as uow:
            run = uow.connection.execute(
                """
                SELECT dataset_id, strategy_id, strategy_parameters, execution_policy,
                       formula_version, status, initial_cash, final_equity,
                       total_return_percent, max_drawdown_percent,
                       win_rate_percent, exposure_percent, trade_count,
                       error_message, started_at, finished_at,
                       artifact_storage_provider, artifact_storage_key,
                       artifact_checksum_sha256, artifact_byte_size
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

        artifact_payload = self._artifact_from_row(run[16:20])
        artifact = (
            BacktestArtifactReference.model_validate(artifact_payload)
            if artifact_payload
            else None
        )
        if artifact is not None:
            self.blob_store.read_bytes(
                artifact.storage_key,
                expected_checksum=artifact.checksum_sha256,
            )
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
            win_rate_percent=Decimal(run[10]),
            exposure_percent=Decimal(run[11]),
            trade_count=int(run[12]),
            error_message=str(run[13]) if run[13] is not None else None,
            started_at=run[14],
            finished_at=run[15],
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
            artifact=artifact,
        )


def default_runtime_replay_repository() -> TradingReplayRuntimeRepository:
    return TradingReplayRuntimeRepository()
