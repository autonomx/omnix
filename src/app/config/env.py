"""Typed environment access. This is the only package allowed to read os.environ."""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping
import os
from threading import Lock
from urllib.parse import urlsplit

_READ_LOCK = Lock()
_READ_NAMES: set[str] = set()


def environment() -> MutableMapping[str, str]:
    return os.environ


def _record(name: str) -> None:
    with _READ_LOCK:
        _READ_NAMES.add(name)


def read_names() -> tuple[str, ...]:
    with _READ_LOCK:
        return tuple(sorted(_READ_NAMES))


def env_str(name: str, default: str | None = None, *, env: Mapping[str, str] | None = None) -> str | None:
    _record(name)
    source = environment() if env is None else env
    value = source.get(name)
    return default if value is None else str(value)


def env_bool(name: str, default: bool = False, *, env: Mapping[str, str] | None = None) -> bool:
    raw = env_str(name, None, env=env)
    if raw is None:
        return default
    value = raw.strip().casefold()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def env_int(name: str, default: int, *, minimum: int | None = None, maximum: int | None = None, env: Mapping[str, str] | None = None) -> int:
    raw = env_str(name, None, env=env)
    try:
        value = default if raw is None else int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return value


def env_list(name: str, default: tuple[str, ...] = (), *, env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    raw = env_str(name, None, env=env)
    if raw is None:
        return default
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def env_url(name: str, default: str | None = None, *, env: Mapping[str, str] | None = None) -> str | None:
    raw = env_str(name, default, env=env)
    if raw is None or not raw.strip():
        return None
    value = raw.strip()
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https", "postgresql", "postgres"} or not parsed.hostname:
        raise ValueError(f"{name} must be an absolute URL")
    return value
