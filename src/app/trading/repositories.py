from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any, Protocol

from app.persistence.errors import RevisionConflict
from app.persistence.tenant import TenantContext, local_tenant_context
from app.persistence.unit_of_work import PostgresUnitOfWork, unit_of_work


TRADING_MODULE = "trading"
SUPPORTED_DOCUMENT_TYPES = frozenset({"workspace", "watchlist", "drawing", "indicator_preset"})


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> AbstractContextManager[PostgresUnitOfWork]: ...


def _record(row: Any) -> dict[str, Any]:
    return {
        "module": str(row[0]),
        "record_type": str(row[1]),
        "record_id": str(row[2]),
        "owner_user_id": str(row[3]) if row[3] is not None else None,
        "payload": dict(row[4]),
        "status": str(row[5]),
        "revision": int(row[6]),
        "expires_at": row[7].isoformat() if row[7] is not None else None,
        "created_at": row[8].isoformat(),
        "updated_at": row[9].isoformat(),
    }


class TradingDocumentRepository:
    """Revisioned Trading documents backed by Omnix PostgreSQL module records."""

    def __init__(
        self,
        *,
        context: TenantContext | None = None,
        uow_factory: UnitOfWorkFactory = unit_of_work,
    ) -> None:
        self.context = context or local_tenant_context()
        self.uow_factory = uow_factory

    @staticmethod
    def _require_type(record_type: str) -> str:
        clean = str(record_type).strip()
        if clean not in SUPPORTED_DOCUMENT_TYPES:
            raise ValueError(f"unsupported Trading document type: {clean}")
        return clean

    def get(self, record_type: str, record_id: str) -> dict[str, Any] | None:
        clean_type = self._require_type(record_type)
        with self.uow_factory() as uow:
            return uow.module_records.get(
                self.context,
                module=TRADING_MODULE,
                record_type=clean_type,
                record_id=record_id,
            )

    def list(self, record_type: str, *, limit: int = 100) -> list[dict[str, Any]]:
        clean_type = self._require_type(record_type)
        with self.uow_factory() as uow:
            return uow.module_records.list(
                self.context,
                module=TRADING_MODULE,
                record_type=clean_type,
                limit=limit,
            )

    def create(self, record_type: str, record_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        clean_type = self._require_type(record_type)
        with self.uow_factory() as uow:
            record = uow.module_records.put(
                self.context,
                module=TRADING_MODULE,
                record_type=clean_type,
                record_id=record_id,
                payload=payload,
            )
            uow.commit()
            return record

    def update(
        self,
        record_type: str,
        record_id: str,
        payload: dict[str, Any],
        *,
        expected_revision: int,
    ) -> dict[str, Any]:
        clean_type = self._require_type(record_type)
        with self.uow_factory() as uow:
            record = uow.module_records.put(
                self.context,
                module=TRADING_MODULE,
                record_type=clean_type,
                record_id=record_id,
                payload=payload,
                expected_revision=expected_revision,
            )
            uow.commit()
            return record

    def archive(
        self,
        record_type: str,
        record_id: str,
        *,
        expected_revision: int,
    ) -> dict[str, Any]:
        clean_type = self._require_type(record_type)
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                """
                UPDATE omnix_module_records
                   SET status = 'archived', revision = revision + 1,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND module = %s AND record_type = %s
                   AND record_id = %s AND revision = %s AND status = 'active'
                RETURNING module, record_type, record_id, owner_user_id, payload,
                          status, revision, expires_at, created_at, updated_at
                """,
                (
                    self.context.workspace_id,
                    TRADING_MODULE,
                    clean_type,
                    record_id,
                    expected_revision,
                ),
            ).fetchone()
            if row is None:
                raise RevisionConflict(
                    f"Trading document expected revision {expected_revision}: {clean_type}/{record_id}"
                )
            uow.commit()
            return _record(row)


RepositoryFactory = Callable[[], TradingDocumentRepository]


def default_trading_repository() -> TradingDocumentRepository:
    return TradingDocumentRepository()
