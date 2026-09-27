from __future__ import annotations

import sys
import uuid
import logging
from types import TracebackType
from typing import Any, Hashable, Literal

from .authority import (
    AuthorityOperation,
    initialize_fresh_install_authority,
    require_authority_operation,
)
from .asset_repository import (
    PostgresAssetRepository,
    PostgresSecretReferenceRepository,
    PostgresSettingsRepository,
)
from .database import PostgresDatabase, default_database
from .execution_repositories import PostgresForegroundSubmissionRepository
from .job_repository import PostgresJobRepository
from .outbox_repository import (
    PostgresOutboxConsumerRepository,
    PostgresOutboxRepository,
    PostgresSideEffectRepository,
)
from .repositories import (
    PostgresAuditRepository,
    PostgresIdempotencyRepository,
    PostgresIdentityRepository,
)
from app.config.env import env_str

from .repository_registry import repository_spec, repository_spec_by_alias
from .transaction_policy import transaction_scope


class UnitOfWorkClosedError(RuntimeError):
    pass


class PostgresUnitOfWork:
    """One explicit transaction shared by all repositories in an operation."""

    def __init__(
        self,
        database: PostgresDatabase | None = None,
        *,
        authority_operation: AuthorityOperation = AuthorityOperation.RUNTIME_MUTATION,
    ) -> None:
        self.database = database or default_database()
        self.authority_operation = authority_operation
        self.connection: Any | None = None
        self.identities: PostgresIdentityRepository
        self.audit: PostgresAuditRepository
        self.idempotency: PostgresIdempotencyRepository
        self.assets: PostgresAssetRepository
        self.settings: PostgresSettingsRepository
        self.secret_references: PostgresSecretReferenceRepository
        self.jobs: PostgresJobRepository
        self.outbox: PostgresOutboxRepository
        self.outbox_consumers: PostgresOutboxConsumerRepository
        self.side_effects: PostgresSideEffectRepository
        self.foreground_submissions: PostgresForegroundSubmissionRepository
        self._connection_context: Any | None = None
        self._transaction_scope_context: Any | None = None
        self._completed = False
        self._after_commit = []
        self._committed = False
        self._feature_repositories: dict[Hashable, Any] = {}

    def __enter__(self) -> "PostgresUnitOfWork":
        if self.connection is not None:
            raise RuntimeError("Unit of Work cannot be entered twice")
        self._connection_context = self.database.connection()
        self.connection = self._connection_context.__enter__()
        try:
            if self.authority_operation == AuthorityOperation.RUNTIME_MUTATION:
                schema_row = self.connection.execute(
                    "SELECT version FROM omnix_schema_migrations ORDER BY version DESC LIMIT 1"
                ).fetchone()
                initialize_fresh_install_authority(
                    self.connection,
                    software_revision=(
                        env_str("OMNIX_SOFTWARE_REVISION", "fresh-install-unversioned")
                        or "fresh-install-unversioned"
                    ).strip(),
                    schema_version=(
                        str(schema_row[0]) if schema_row is not None else "unknown-schema"
                    ),
                )
            require_authority_operation(self.connection, self.authority_operation)
        except BaseException:
            context, self._connection_context = self._connection_context, None
            self.connection = None
            if context is not None:
                context.__exit__(*sys.exc_info())
            raise
        self._transaction_scope_context = transaction_scope()
        self._transaction_scope_context.__enter__()
        self.identities = PostgresIdentityRepository(self.connection)
        self.audit = PostgresAuditRepository(self.connection)
        self.idempotency = PostgresIdempotencyRepository(self.connection)
        self.assets = PostgresAssetRepository(self.connection)
        self.settings = PostgresSettingsRepository(self.connection)
        self.secret_references = PostgresSecretReferenceRepository(self.connection)
        self.jobs = PostgresJobRepository(self.connection)
        self.outbox = PostgresOutboxRepository(self.connection)
        self.outbox_consumers = PostgresOutboxConsumerRepository(self.connection)
        self.side_effects = PostgresSideEffectRepository(self.connection)
        self.foreground_submissions = PostgresForegroundSubmissionRepository(self.connection)
        return self

    def repository(self, repo_type: Hashable):
        connection = self._require_connection()
        if repo_type in self._feature_repositories:
            return self._feature_repositories[repo_type]
        spec = repository_spec(repo_type)
        if spec is None:
            raise KeyError(f"repository is not registered: {repo_type!r}")
        value = spec.factory(connection)
        self._feature_repositories[repo_type] = value
        return value

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        spec = repository_spec_by_alias(name)
        if spec is None:
            raise AttributeError(name)
        return self.repository(spec.type)

    def commit(self) -> None:
        connection = self._require_connection()
        connection.commit()
        self._completed = True
        self._committed = True

    def rollback(self) -> None:
        connection = self._require_connection()
        connection.rollback()
        self._completed = True
        self._committed = False

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        connection = self._require_connection()
        try:
            if exc_type is not None or not self._completed:
                connection.rollback()
        finally:
            transaction_context, self._transaction_scope_context = (
                self._transaction_scope_context,
                None,
            )
            context, self._connection_context = self._connection_context, None
            self.connection = None
            self._completed = True
            if transaction_context is not None:
                transaction_context.__exit__(exc_type, exc, traceback)
            if context is not None:
                context.__exit__(exc_type, exc, traceback)
        if self._committed and exc_type is None:
            for callback in self._after_commit:
                try:
                    callback()
                except Exception:
                    logging.getLogger(__name__).exception('Post-commit maintenance failed')
        return False

    def _require_connection(self) -> Any:
        if self.connection is None:
            raise UnitOfWorkClosedError("Unit of Work is not active")
        return self.connection


def unit_of_work(
    database: PostgresDatabase | None = None,
    *,
    authority_operation: AuthorityOperation = AuthorityOperation.RUNTIME_MUTATION,
):
    from .transaction_binding import shared_work

    resolved = database or default_database()
    parent = shared_work(resolved)
    if parent is not None:
        if parent.authority_operation != authority_operation:
            raise RuntimeError('A shared transaction cannot change its authority operation')
        return _JoinedUnitOfWork(parent)
    return PostgresUnitOfWork(resolved, authority_operation=authority_operation)


class _JoinedUnitOfWork:
    """Nested repository operation: commit releases a savepoint, never the root."""

    def __init__(self, parent):
        self.parent = parent
        self.name = f'omnix_join_{uuid.uuid4().hex}'
        self.completed = False

    def __getattr__(self, name):
        return getattr(self.parent, name)

    def __enter__(self):
        self.parent._require_connection().execute(f'SAVEPOINT {self.name}')
        self.callback_count = len(self.parent._after_commit)
        return self

    def commit(self):
        self.completed = True

    def rollback(self):
        self.parent._require_connection().execute(f'ROLLBACK TO SAVEPOINT {self.name}')
        del self.parent._after_commit[self.callback_count:]
        self.completed = True

    def __exit__(self, exc_type, exc, traceback):
        connection = self.parent._require_connection()
        if exc_type is not None or not self.completed:
            connection.execute(f'ROLLBACK TO SAVEPOINT {self.name}')
            del self.parent._after_commit[self.callback_count:]
        connection.execute(f'RELEASE SAVEPOINT {self.name}')
        return False
