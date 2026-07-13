from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from time import perf_counter
from typing import Any, Iterator

from .config import DatabaseSettings, database_settings


class DatabaseUnavailableError(RuntimeError):
    """Raised when the authoritative PostgreSQL service cannot be reached."""


class PostgresDatabase:
    """Lazy synchronous PostgreSQL connection pool shared by application services."""

    def __init__(self, settings: DatabaseSettings | None = None) -> None:
        self.settings = settings or database_settings()
        self._pool: Any | None = None

    def open(self, *, wait: bool = True) -> None:
        if self._pool is not None:
            return
        try:
            from psycopg_pool import ConnectionPool
        except ImportError as exc:  # pragma: no cover - packaging failure
            raise RuntimeError(
                "PostgreSQL dependencies are missing; install psycopg[binary] and psycopg-pool"
            ) from exc

        def configure(connection: Any) -> None:
            # psycopg_pool requires configure callbacks to return an idle
            # connection. Apply session settings and commit them explicitly so
            # the first borrower never inherits an open setup transaction.
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('TimeZone', 'UTC', false)")
                cursor.execute(
                    "SELECT set_config('statement_timeout', %s, false)",
                    (str(self.settings.statement_timeout_ms),),
                )
            connection.commit()

        self._pool = ConnectionPool(
            conninfo=self.settings.url,
            min_size=self.settings.pool_min,
            max_size=self.settings.pool_max,
            timeout=float(self.settings.connect_timeout_seconds),
            kwargs={
                "autocommit": False,
                "connect_timeout": self.settings.connect_timeout_seconds,
                "application_name": self.settings.application_name,
            },
            configure=configure,
            open=True,
        )
        if wait:
            try:
                self._pool.wait(timeout=float(self.settings.connect_timeout_seconds))
            except Exception as exc:
                self.close()
                raise DatabaseUnavailableError(
                    f"PostgreSQL is unavailable at {self.settings.redacted_url}"
                ) from exc

    def close(self) -> None:
        pool, self._pool = self._pool, None
        if pool is not None:
            pool.close()

    @contextmanager
    def connection(self) -> Iterator[Any]:
        self.open()
        assert self._pool is not None
        try:
            with self._pool.connection() as connection:
                yield connection
        except Exception as exc:
            if exc.__class__.__module__.startswith("psycopg"):
                raise DatabaseUnavailableError("PostgreSQL operation failed") from exc
            raise

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        with self.connection() as connection:
            with connection.transaction():
                yield connection

    def health(self) -> dict[str, Any]:
        started = perf_counter()
        try:
            with self.connection() as connection:
                row = connection.execute(
                    "SELECT current_database(), current_user, "
                    "current_setting('server_version_num')::integer"
                ).fetchone()
        except Exception as exc:
            return {
                "ok": False,
                "backend": "postgresql",
                "database_url": self.settings.redacted_url,
                "latency_ms": round((perf_counter() - started) * 1000.0, 3),
                "error": exc.__class__.__name__,
            }
        return {
            "ok": True,
            "backend": "postgresql",
            "database_url": self.settings.redacted_url,
            "database": str(row[0]),
            "user": str(row[1]),
            "server_version_num": int(row[2]),
            "latency_ms": round((perf_counter() - started) * 1000.0, 3),
        }


@lru_cache(maxsize=1)
def default_database() -> PostgresDatabase:
    return PostgresDatabase(database_settings())


def close_default_database() -> None:
    if default_database.cache_info().currsize:
        default_database().close()
    default_database.cache_clear()
