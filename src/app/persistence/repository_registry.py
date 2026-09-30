"""Composable feature repository registry for PostgreSQL units of work."""
from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any, Callable, Hashable

RepositoryFactory = Callable[[Any], Any]


@dataclass(frozen=True, slots=True)
class RepositorySpec:
    type: Hashable
    factory: RepositoryFactory
    alias: str | None = None


_LOCK = RLock()
_SPECS_BY_TYPE: dict[Hashable, RepositorySpec] = {}
_SPECS_BY_ALIAS: dict[str, RepositorySpec] = {}


def install_repository_specs(specs: tuple[RepositorySpec, ...]) -> None:
    with _LOCK:
        for spec in specs:
            existing = _SPECS_BY_TYPE.get(spec.type)
            if existing is not None and existing != spec:
                raise ValueError(f"duplicate repository type: {spec.type!r}")
            if spec.alias:
                alias_existing = _SPECS_BY_ALIAS.get(spec.alias)
                if alias_existing is not None and alias_existing != spec:
                    raise ValueError(f"duplicate repository alias: {spec.alias}")
                _SPECS_BY_ALIAS[spec.alias] = spec
            _SPECS_BY_TYPE[spec.type] = spec


def register_repository_specs(specs: tuple[RepositorySpec, ...]) -> None:
    """Register feature-owned repository providers during composition."""
    install_repository_specs(specs)


def repository_spec(repo_type: Hashable) -> RepositorySpec | None:
    with _LOCK:
        return _SPECS_BY_TYPE.get(repo_type)


def repository_spec_by_alias(alias: str) -> RepositorySpec | None:
    with _LOCK:
        return _SPECS_BY_ALIAS.get(alias)


def reset_repository_specs() -> None:
    with _LOCK:
        _SPECS_BY_TYPE.clear()
        _SPECS_BY_ALIAS.clear()


def registered_repository_aliases() -> tuple[str, ...]:
    with _LOCK:
        return tuple(sorted(_SPECS_BY_ALIAS))


def clear_repository_specs_for_tests() -> None:
    reset_repository_specs()
