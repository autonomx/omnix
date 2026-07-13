from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .database import PostgresDatabase, default_database


_MIGRATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS omnix_schema_migrations (
    version TEXT PRIMARY KEY,
    checksum TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL,
    execution_ms DOUBLE PRECISION NOT NULL
)
"""


class MigrationError(RuntimeError):
    pass


class MigrationDriftError(MigrationError):
    pass


@dataclass(frozen=True, slots=True)
class Migration:
    version: str
    path: Path
    checksum: str
    sql: str


def migration_root() -> Path:
    return Path(__file__).with_name("migrations")


def discover_migrations(root: Path | None = None) -> list[Migration]:
    resolved = root or migration_root()
    migrations: list[Migration] = []
    for path in sorted(resolved.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        migrations.append(
            Migration(
                version=path.stem,
                path=path,
                checksum=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
                sql=sql,
            )
        )
    versions = [migration.version for migration in migrations]
    if versions != sorted(set(versions)):
        raise MigrationError("migration versions must be unique and lexically ordered")
    return migrations


def _applied(connection: Any) -> dict[str, dict[str, Any]]:
    connection.execute(_MIGRATION_TABLE_SQL)
    rows = connection.execute(
        "SELECT version, checksum, applied_at, execution_ms "
        "FROM omnix_schema_migrations ORDER BY version"
    ).fetchall()
    return {
        str(row[0]): {
            "checksum": str(row[1]),
            "applied_at": row[2].isoformat(),
            "execution_ms": float(row[3]),
        }
        for row in rows
    }


def migration_status(
    database: PostgresDatabase | None = None,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    db = database or default_database()
    discovered = discover_migrations(root)
    with db.transaction() as connection:
        applied = _applied(connection)
    drift: list[str] = []
    pending: list[str] = []
    known_versions = {migration.version for migration in discovered}
    for migration in discovered:
        record = applied.get(migration.version)
        if record is None:
            pending.append(migration.version)
        elif record["checksum"] != migration.checksum:
            drift.append(migration.version)
    unknown = sorted(set(applied) - known_versions)
    return {
        "ok": not drift and not unknown,
        "discovered": [migration.version for migration in discovered],
        "applied": sorted(applied),
        "pending": pending,
        "checksum_drift": drift,
        "unknown_applied": unknown,
        "records": applied,
    }


def apply_migrations(
    database: PostgresDatabase | None = None,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    from time import perf_counter

    db = database or default_database()
    migrations = discover_migrations(root)
    applied_now: list[str] = []
    with db.transaction() as connection:
        applied = _applied(connection)
        known_versions = {migration.version for migration in migrations}
        unknown = sorted(set(applied) - known_versions)
        if unknown:
            raise MigrationDriftError(f"database contains unknown migrations: {unknown}")
        for migration in migrations:
            record = applied.get(migration.version)
            if record is not None:
                if record["checksum"] != migration.checksum:
                    raise MigrationDriftError(
                        f"migration checksum drift for {migration.version}"
                    )
                continue
            started = perf_counter()
            connection.execute(migration.sql, prepare=False)
            elapsed_ms = (perf_counter() - started) * 1000.0
            connection.execute(
                "INSERT INTO omnix_schema_migrations "
                "(version, checksum, applied_at, execution_ms) VALUES (%s, %s, %s, %s)",
                (
                    migration.version,
                    migration.checksum,
                    datetime.now(timezone.utc),
                    elapsed_ms,
                ),
            )
            applied_now.append(migration.version)
    status = migration_status(db, root=root)
    status["applied_now"] = applied_now
    return status
