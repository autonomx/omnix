from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import Any

from .database import PostgresDatabase, default_database
from .migrations import apply_migrations, assert_schema_compatible, migration_status


class PersistenceMode(str, Enum):
    POSTGRESQL = "postgresql"
    LEGACY_TEST = "legacy_test"
    LEGACY_IMPORT = "legacy_import"


class LegacyPersistenceRetired(RuntimeError):
    """Raised when normal runtime attempts to use retired SQLite/JSON authority."""


class PersistenceReadinessError(RuntimeError):
    """Raised when PostgreSQL is not ready to serve authoritative runtime state."""


@dataclass(frozen=True, slots=True)
class RuntimePersistenceStatus:
    mode: PersistenceMode
    backend: str
    ready: bool
    cutover_mode: str | None
    migrations_pending: tuple[str, ...]
    details: dict[str, Any]


def _under_pytest() -> bool:
    return "pytest" in sys.modules or bool(os.environ.get("PYTEST_CURRENT_TEST"))


@lru_cache(maxsize=1)
def persistence_mode() -> PersistenceMode:
    raw = (os.environ.get("OMNIX_PERSISTENCE_MODE") or "postgresql").strip().lower()
    try:
        mode = PersistenceMode(raw)
    except ValueError as exc:
        raise PersistenceReadinessError(
            "OMNIX_PERSISTENCE_MODE must be postgresql, legacy_test, or legacy_import"
        ) from exc
    if mode == PersistenceMode.LEGACY_TEST:
        allowed = (os.environ.get("OMNIX_ALLOW_LEGACY_TEST_PERSISTENCE") or "").strip() == "1"
        if not allowed or not (_under_pytest() or os.environ.get("CI")):
            raise LegacyPersistenceRetired(
                "legacy_test persistence is restricted to explicit CI or pytest execution"
            )
    if mode == PersistenceMode.LEGACY_IMPORT:
        allowed = (os.environ.get("OMNIX_ALLOW_LEGACY_IMPORT") or "").strip() == "1"
        if not allowed:
            raise LegacyPersistenceRetired(
                "legacy_import persistence requires OMNIX_ALLOW_LEGACY_IMPORT=1"
            )
    return mode


def reset_persistence_mode_cache() -> None:
    persistence_mode.cache_clear()


def require_legacy_persistence(*, purpose: str) -> None:
    mode = persistence_mode()
    if mode not in {PersistenceMode.LEGACY_TEST, PersistenceMode.LEGACY_IMPORT}:
        raise LegacyPersistenceRetired(
            f"{purpose} uses retired legacy persistence; run the PostgreSQL migration "
            "or invoke an explicit legacy import/test tool"
        )


def uses_postgresql_runtime() -> bool:
    return persistence_mode() == PersistenceMode.POSTGRESQL


def _domain_row_count(connection: Any) -> int:
    tables = (
        "omnix_chat_sessions",
        "omnix_characters",
        "omnix_memory_records",
        "omnix_jobs",
        "omnix_assets",
        "omnix_rpg_campaigns",
        "omnix_provider_configs",
        "omnix_prompt_templates",
        "omnix_research_records",
        "omnix_reports",
        "omnix_module_records",
    )
    expressions = ", ".join(f"(SELECT COUNT(*) FROM {table})" for table in tables)
    row = connection.execute(f"SELECT {expressions}").fetchone()
    return sum(int(value) for value in row)


def _ensure_fresh_install_cutover(database: PostgresDatabase) -> str:
    with database.transaction() as connection:
        row = connection.execute(
            "SELECT mode FROM omnix_persistence_cutover WHERE singleton = TRUE FOR UPDATE"
        ).fetchone()
        if row is None:
            connection.execute(
                "INSERT INTO omnix_persistence_cutover (singleton, mode) "
                "VALUES (TRUE, 'legacy_preflight')"
            )
            mode = "legacy_preflight"
        else:
            mode = str(row[0])
        if mode == "legacy_preflight":
            imports = int(
                connection.execute(
                    "SELECT COUNT(*) FROM omnix_legacy_import_runs"
                ).fetchone()[0]
            )
            if imports == 0 and _domain_row_count(connection) == 0:
                connection.execute(
                    """
                    UPDATE omnix_persistence_cutover
                       SET mode = 'postgresql',
                           activated_at = CURRENT_TIMESTAMP,
                           updated_at = CURRENT_TIMESTAMP,
                           metadata = metadata || jsonb_build_object(
                               'fresh_installation', TRUE,
                               'legacy_import_required', FALSE
                           )
                     WHERE singleton = TRUE
                    """
                )
                mode = "postgresql"
        return mode


def ensure_postgresql_runtime_ready(
    database: PostgresDatabase | None = None,
    *,
    auto_initialize_fresh_install: bool = True,
) -> RuntimePersistenceStatus:
    mode = persistence_mode()
    if mode != PersistenceMode.POSTGRESQL:
        return RuntimePersistenceStatus(
            mode=mode,
            backend="legacy",
            ready=True,
            cutover_mode=None,
            migrations_pending=(),
            details={"restricted_mode": True},
        )
    db = database or default_database()
    health = db.health()
    if health.get("ok") is not True:
        raise PersistenceReadinessError("PostgreSQL health check failed")
    apply_migrations(db)
    migrations = migration_status(db)
    pending = tuple(str(item) for item in migrations.get("pending") or ())
    try:
        assert_schema_compatible(migrations)
    except Exception as exc:
        raise PersistenceReadinessError(str(exc)) from exc
    if not migrations.get("ok") or pending:
        raise PersistenceReadinessError(
            f"PostgreSQL migration state is not ready: pending={list(pending)}"
        )
    if auto_initialize_fresh_install:
        cutover_mode = _ensure_fresh_install_cutover(db)
    else:
        with db.connection() as connection:
            row = connection.execute(
                "SELECT mode FROM omnix_persistence_cutover WHERE singleton = TRUE"
            ).fetchone()
        cutover_mode = str(row[0]) if row is not None else None
    if cutover_mode != "postgresql":
        raise PersistenceReadinessError(
            "PostgreSQL runtime is not activated. Complete or verify the legacy import "
            "and run the cutover activation command."
        )
    with db.connection() as connection:
        runtime = connection.execute(
            """
            SELECT backend, runtime_schema_version, legacy_runtime_enabled, metadata
              FROM omnix_runtime_persistence_state WHERE singleton = TRUE
            """
        ).fetchone()
    if runtime is None or str(runtime[0]) != "postgresql" or bool(runtime[2]):
        raise PersistenceReadinessError("runtime persistence retirement marker is invalid")
    return RuntimePersistenceStatus(
        mode=mode,
        backend="postgresql",
        ready=True,
        cutover_mode=cutover_mode,
        migrations_pending=pending,
        details={
            "health": health,
            "runtime_schema_version": str(runtime[1]),
            "application_schema_min": migrations.get("application_schema_min"),
            "application_schema_max": migrations.get("application_schema_max"),
            "metadata": dict(runtime[3]),
        },
    )
