from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlparse


_DEFAULT_DATABASE_URL = "postgresql://omnix:omnix@127.0.0.1:5432/omnix"


class DatabaseConfigurationError(ValueError):
    """Raised when authoritative persistence configuration is unsafe or invalid."""


def _integer(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise DatabaseConfigurationError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise DatabaseConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    url: str
    pool_min: int = 1
    pool_max: int = 10
    connect_timeout_seconds: int = 5
    statement_timeout_ms: int = 30_000
    application_name: str = "omnix"

    def __post_init__(self) -> None:
        parsed = urlparse(self.url)
        if parsed.scheme not in {"postgresql", "postgres"}:
            raise DatabaseConfigurationError(
                "OMNIX_DATABASE_URL must use postgresql://; SQLite is not a supported runtime backend"
            )
        if not parsed.hostname:
            raise DatabaseConfigurationError("OMNIX_DATABASE_URL must include a host")
        if not parsed.path or parsed.path == "/":
            raise DatabaseConfigurationError("OMNIX_DATABASE_URL must include a database name")
        if self.pool_min < 0:
            raise DatabaseConfigurationError("pool_min cannot be negative")
        if self.pool_max < 1 or self.pool_max < self.pool_min:
            raise DatabaseConfigurationError("pool_max must be positive and >= pool_min")
        if self.connect_timeout_seconds < 1:
            raise DatabaseConfigurationError("connect timeout must be positive")
        if self.statement_timeout_ms < 100:
            raise DatabaseConfigurationError("statement timeout must be at least 100ms")

    @property
    def redacted_url(self) -> str:
        parsed = urlparse(self.url)
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        database = parsed.path.lstrip("/")
        username = parsed.username or ""
        user = f"{username}:***@" if username else ""
        return f"postgresql://{user}{host}{port}/{database}"


@lru_cache(maxsize=1)
def database_settings() -> DatabaseSettings:
    pool_min = _integer("OMNIX_DATABASE_POOL_MIN", 1, minimum=0, maximum=100)
    pool_max = _integer("OMNIX_DATABASE_POOL_MAX", 10, minimum=1, maximum=200)
    return DatabaseSettings(
        url=(os.environ.get("OMNIX_DATABASE_URL") or _DEFAULT_DATABASE_URL).strip(),
        pool_min=pool_min,
        pool_max=pool_max,
        connect_timeout_seconds=_integer(
            "OMNIX_DATABASE_CONNECT_TIMEOUT", 5, minimum=1, maximum=120
        ),
        statement_timeout_ms=_integer(
            "OMNIX_DATABASE_STATEMENT_TIMEOUT", 30_000, minimum=100, maximum=3_600_000
        ),
        application_name=(os.environ.get("OMNIX_DATABASE_APPLICATION_NAME") or "omnix").strip()
        or "omnix",
    )


def reset_database_settings_cache() -> None:
    database_settings.cache_clear()
