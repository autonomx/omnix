from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from app.persistence.errors import RevisionConflict
from app.persistence.tenant import TenantContext, local_tenant_context
from app.persistence.unit_of_work import PostgresUnitOfWork, unit_of_work

from .scanner import (
    ScannerRunStatus,
    TradingScannerDefinition,
    TradingScannerResult,
    TradingScannerRun,
)


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> AbstractContextManager[PostgresUnitOfWork]: ...


def _definition(row) -> TradingScannerDefinition:
    return TradingScannerDefinition(
        scanner_id=str(row[0]),
        name=str(row[1]),
        instrument_ids=list(row[2] or []),
        binding_ids=dict(row[3] or {}),
        interval=str(row[4]),
        history_limit=int(row[5]),
        rules=list(row[6] or []),
        max_concurrency=int(row[7]),
        request_timeout_seconds=float(row[8]),
        run_timeout_seconds=float(row[9]),
        formula_version=str(row[10]),
        enabled=bool(row[11]),
        revision=int(row[12]),
        created_at=row[13],
        updated_at=row[14],
    )


def _run(row) -> TradingScannerRun:
    return TradingScannerRun(
        run_id=str(row[0]),
        scanner_id=str(row[1]),
        status=str(row[2]),
        cancellation_requested=bool(row[3]),
        universe_count=int(row[4]),
        completed_count=int(row[5]),
        matched_count=int(row[6]),
        started_at=row[7],
        finished_at=row[8],
        error_message=str(row[9]) if row[9] is not None else None,
        definition_snapshot=dict(row[10] or {}),
        created_at=row[11],
        updated_at=row[12],
    )


def _result(row) -> TradingScannerResult:
    return TradingScannerResult(
        run_id=str(row[0]),
        instrument_id=str(row[1]),
        requested_binding_id=str(row[2]) if row[2] is not None else None,
        resolved_binding_id=str(row[3]),
        provider=str(row[4]),
        dataset_fingerprint=str(row[5]),
        source_as_of=row[6],
        formula_version=str(row[7]),
        metrics={key: Decimal(str(value)) for key, value in dict(row[8] or {}).items()},
        matched_rules=list(row[9] or []),
        rank=int(row[10]),
        score=Decimal(row[11]),
    )


_DEFINITION_COLUMNS = """
    scanner_id, name, instrument_ids, binding_ids, interval, history_limit,
    rules, max_concurrency, request_timeout_seconds, run_timeout_seconds,
    formula_version, enabled, revision, created_at, updated_at
"""
_RUN_COLUMNS = """
    run_id, scanner_id, status, cancellation_requested, universe_count,
    completed_count, matched_count, started_at, finished_at, error_message,
    definition_snapshot, created_at, updated_at
"""
_RESULT_COLUMNS = """
    run_id, instrument_id, requested_binding_id, resolved_binding_id, provider,
    dataset_fingerprint, source_as_of, formula_version, metrics, matched_rules,
    rank, score
"""


class TradingScannerRepository:
    def __init__(
        self,
        *,
        context: TenantContext | None = None,
        uow_factory: UnitOfWorkFactory = unit_of_work,
    ) -> None:
        self.context = context or local_tenant_context()
        self.uow_factory = uow_factory

    def list_definitions(self, limit: int = 100) -> list[TradingScannerDefinition]:
        with self.uow_factory() as uow:
            rows = uow.connection.execute(
                f"SELECT {_DEFINITION_COLUMNS} FROM omnix_trading_scanners WHERE workspace_id = %s ORDER BY updated_at DESC LIMIT %s",
                (self.context.workspace_id, limit),
            ).fetchall()
            return [_definition(row) for row in rows]

    def get_definition(self, scanner_id: str) -> TradingScannerDefinition | None:
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                f"SELECT {_DEFINITION_COLUMNS} FROM omnix_trading_scanners WHERE workspace_id = %s AND scanner_id = %s",
                (self.context.workspace_id, scanner_id),
            ).fetchone()
            return _definition(row) if row else None

    def create_definition(self, definition: TradingScannerDefinition) -> TradingScannerDefinition:
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                f"""
                INSERT INTO omnix_trading_scanners (
                    workspace_id, scanner_id, owner_user_id, name, instrument_ids,
                    binding_ids, interval, history_limit, rules, max_concurrency,
                    request_timeout_seconds, run_timeout_seconds, formula_version, enabled
                ) VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
                RETURNING {_DEFINITION_COLUMNS}
                """,
                (
                    self.context.workspace_id,
                    definition.scanner_id,
                    self.context.user_id,
                    definition.name,
                    json.dumps(definition.instrument_ids),
                    json.dumps(definition.binding_ids),
                    definition.interval,
                    definition.history_limit,
                    json.dumps([rule.model_dump(mode="json") for rule in definition.rules]),
                    definition.max_concurrency,
                    definition.request_timeout_seconds,
                    definition.run_timeout_seconds,
                    definition.formula_version,
                    definition.enabled,
                ),
            ).fetchone()
            uow.commit()
            return _definition(row)

    def update_definition(
        self,
        scanner_id: str,
        definition: TradingScannerDefinition,
        expected_revision: int,
    ) -> TradingScannerDefinition:
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                f"""
                UPDATE omnix_trading_scanners
                   SET name = %s, instrument_ids = %s::jsonb, binding_ids = %s::jsonb,
                       interval = %s, history_limit = %s, rules = %s::jsonb,
                       max_concurrency = %s, request_timeout_seconds = %s,
                       run_timeout_seconds = %s, formula_version = %s, enabled = %s,
                       revision = revision + 1, updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND scanner_id = %s AND revision = %s
                RETURNING {_DEFINITION_COLUMNS}
                """,
                (
                    definition.name,
                    json.dumps(definition.instrument_ids),
                    json.dumps(definition.binding_ids),
                    definition.interval,
                    definition.history_limit,
                    json.dumps([rule.model_dump(mode="json") for rule in definition.rules]),
                    definition.max_concurrency,
                    definition.request_timeout_seconds,
                    definition.run_timeout_seconds,
                    definition.formula_version,
                    definition.enabled,
                    self.context.workspace_id,
                    scanner_id,
                    expected_revision,
                ),
            ).fetchone()
            if row is None:
                raise RevisionConflict(f"Trading scanner expected revision {expected_revision}: {scanner_id}")
            uow.commit()
            return _definition(row)

    def create_run(self, run: TradingScannerRun) -> TradingScannerRun:
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                f"""
                INSERT INTO omnix_trading_scanner_runs (
                    workspace_id, run_id, scanner_id, status, universe_count,
                    definition_snapshot
                ) VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                RETURNING {_RUN_COLUMNS}
                """,
                (
                    self.context.workspace_id,
                    run.run_id,
                    run.scanner_id,
                    run.status,
                    run.universe_count,
                    json.dumps(run.definition_snapshot),
                ),
            ).fetchone()
            uow.commit()
            return _run(row)

    def update_run(
        self,
        run_id: str,
        *,
        status: ScannerRunStatus,
        completed_count: int,
        matched_count: int,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        error_message: str | None = None,
    ) -> TradingScannerRun:
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                f"""
                UPDATE omnix_trading_scanner_runs
                   SET status = %s, completed_count = %s, matched_count = %s,
                       started_at = COALESCE(%s, started_at), finished_at = %s,
                       error_message = %s, updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND run_id = %s
                RETURNING {_RUN_COLUMNS}
                """,
                (
                    status,
                    completed_count,
                    matched_count,
                    started_at,
                    finished_at,
                    error_message,
                    self.context.workspace_id,
                    run_id,
                ),
            ).fetchone()
            uow.commit()
            return _run(row)

    def request_cancellation(self, run_id: str) -> None:
        with self.uow_factory() as uow:
            uow.connection.execute(
                "UPDATE omnix_trading_scanner_runs SET cancellation_requested = TRUE, updated_at = CURRENT_TIMESTAMP WHERE workspace_id = %s AND run_id = %s",
                (self.context.workspace_id, run_id),
            )
            uow.commit()

    def replace_results(self, run_id: str, results: list[TradingScannerResult]) -> None:
        with self.uow_factory() as uow:
            uow.connection.execute(
                "DELETE FROM omnix_trading_scanner_results WHERE workspace_id = %s AND run_id = %s",
                (self.context.workspace_id, run_id),
            )
            for result in results:
                uow.connection.execute(
                    """
                    INSERT INTO omnix_trading_scanner_results (
                        workspace_id, run_id, instrument_id, requested_binding_id,
                        resolved_binding_id, provider, dataset_fingerprint, source_as_of,
                        formula_version, metrics, matched_rules, rank, score
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
                    """,
                    (
                        self.context.workspace_id,
                        run_id,
                        result.instrument_id,
                        result.requested_binding_id,
                        result.resolved_binding_id,
                        result.provider,
                        result.dataset_fingerprint,
                        result.source_as_of,
                        result.formula_version,
                        json.dumps({key: str(value) for key, value in result.metrics.items()}),
                        json.dumps(result.matched_rules),
                        result.rank,
                        result.score,
                    ),
                )
            uow.commit()

    def list_runs(self, scanner_id: str | None = None, limit: int = 100) -> list[TradingScannerRun]:
        with self.uow_factory() as uow:
            if scanner_id:
                rows = uow.connection.execute(
                    f"SELECT {_RUN_COLUMNS} FROM omnix_trading_scanner_runs WHERE workspace_id = %s AND scanner_id = %s ORDER BY created_at DESC LIMIT %s",
                    (self.context.workspace_id, scanner_id, limit),
                ).fetchall()
            else:
                rows = uow.connection.execute(
                    f"SELECT {_RUN_COLUMNS} FROM omnix_trading_scanner_runs WHERE workspace_id = %s ORDER BY created_at DESC LIMIT %s",
                    (self.context.workspace_id, limit),
                ).fetchall()
            return [_run(row) for row in rows]

    def list_results(self, run_id: str, limit: int = 500) -> list[TradingScannerResult]:
        with self.uow_factory() as uow:
            rows = uow.connection.execute(
                f"SELECT {_RESULT_COLUMNS} FROM omnix_trading_scanner_results WHERE workspace_id = %s AND run_id = %s ORDER BY rank, instrument_id LIMIT %s",
                (self.context.workspace_id, run_id, limit),
            ).fetchall()
            return [_result(row) for row in rows]


ScannerRepositoryFactory = Callable[[], TradingScannerRepository]


def default_scanner_repository() -> TradingScannerRepository:
    return TradingScannerRepository()
