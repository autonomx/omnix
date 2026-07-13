from __future__ import annotations

from types import TracebackType
from typing import Any

from .asset_repository import (
    PostgresAssetRepository,
    PostgresSecretReferenceRepository,
    PostgresSettingsRepository,
)
from .conversation_repositories import (
    PostgresCharacterRepository,
    PostgresChatRepository,
    PostgresMemoryRepository,
)
from .database import PostgresDatabase, default_database
from .execution_repositories import (
    PostgresForegroundSubmissionRepository,
    PostgresOutboxRepository,
)
from .job_repository import PostgresJobRepository
from .repositories import (
    PostgresAuditRepository,
    PostgresIdempotencyRepository,
    PostgresIdentityRepository,
)


class UnitOfWorkClosedError(RuntimeError):
    pass


class PostgresUnitOfWork:
    """One explicit transaction shared by all repositories in an operation."""

    def __init__(self, database: PostgresDatabase | None = None) -> None:
        self.database = database or default_database()
        self.connection: Any | None = None
        self.identities: PostgresIdentityRepository
        self.audit: PostgresAuditRepository
        self.idempotency: PostgresIdempotencyRepository
        self.assets: PostgresAssetRepository
        self.settings: PostgresSettingsRepository
        self.secret_references: PostgresSecretReferenceRepository
        self.characters: PostgresCharacterRepository
        self.memories: PostgresMemoryRepository
        self.chats: PostgresChatRepository
        self.jobs: PostgresJobRepository
        self.outbox: PostgresOutboxRepository
        self.foreground_submissions: PostgresForegroundSubmissionRepository
        self._connection_context: Any | None = None
        self._completed = False

    def __enter__(self) -> "PostgresUnitOfWork":
        if self.connection is not None:
            raise RuntimeError("Unit of Work cannot be entered twice")
        self._connection_context = self.database.connection()
        self.connection = self._connection_context.__enter__()
        self.identities = PostgresIdentityRepository(self.connection)
        self.audit = PostgresAuditRepository(self.connection)
        self.idempotency = PostgresIdempotencyRepository(self.connection)
        self.assets = PostgresAssetRepository(self.connection)
        self.settings = PostgresSettingsRepository(self.connection)
        self.secret_references = PostgresSecretReferenceRepository(self.connection)
        self.characters = PostgresCharacterRepository(self.connection)
        self.memories = PostgresMemoryRepository(self.connection)
        self.chats = PostgresChatRepository(self.connection)
        self.jobs = PostgresJobRepository(self.connection)
        self.outbox = PostgresOutboxRepository(self.connection)
        self.foreground_submissions = PostgresForegroundSubmissionRepository(self.connection)
        return self

    def commit(self) -> None:
        connection = self._require_connection()
        connection.commit()
        self._completed = True

    def rollback(self) -> None:
        connection = self._require_connection()
        connection.rollback()
        self._completed = True

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        connection = self._require_connection()
        try:
            if exc_type is not None or not self._completed:
                connection.rollback()
        finally:
            context, self._connection_context = self._connection_context, None
            self.connection = None
            self._completed = True
            if context is not None:
                context.__exit__(exc_type, exc, traceback)
        return False

    def _require_connection(self) -> Any:
        if self.connection is None:
            raise UnitOfWorkClosedError("Unit of Work is not active")
        return self.connection


def unit_of_work(database: PostgresDatabase | None = None) -> PostgresUnitOfWork:
    return PostgresUnitOfWork(database)
