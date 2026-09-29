from __future__ import annotations

from contextlib import contextmanager
from importlib import import_module

import pytest

from app.persistence import repository_registry
from app.persistence.repository_registry import RepositorySpec

unit_of_work_module = import_module("app.persistence.unit_of_work")


class _FeatureRepositoryPort:
    pass


class _Connection:
    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


class _Database:
    def __init__(self) -> None:
        self.connection_value = _Connection()

    @contextmanager
    def connection(self):
        yield self.connection_value


@pytest.fixture
def isolated_repository_registry():
    with repository_registry._LOCK:
        prior_types = dict(repository_registry._SPECS_BY_TYPE)
        prior_aliases = dict(repository_registry._SPECS_BY_ALIAS)
    try:
        yield repository_registry.install_repository_specs
    finally:
        with repository_registry._LOCK:
            repository_registry._SPECS_BY_TYPE.clear()
            repository_registry._SPECS_BY_TYPE.update(prior_types)
            repository_registry._SPECS_BY_ALIAS.clear()
            repository_registry._SPECS_BY_ALIAS.update(prior_aliases)


def test_feature_repository_factories_are_lazy_and_cached_per_unit_of_work(
    monkeypatch,
    isolated_repository_registry,
) -> None:
    constructed_with = []

    def make_repository(connection):
        constructed_with.append(connection)
        return object()

    spec = RepositorySpec(
        type=_FeatureRepositoryPort,
        factory=make_repository,
        alias="feature_repository",
    )
    isolated_repository_registry((spec,))
    monkeypatch.setattr(
        unit_of_work_module,
        "require_authority_operation",
        lambda connection, operation: None,
    )

    work = unit_of_work_module.PostgresUnitOfWork(_Database())
    with work:
        first_connection = work.connection
        assert work.identities is not None
        assert work.jobs is not None
        assert constructed_with == []

        repository = work.repository(_FeatureRepositoryPort)
        assert constructed_with == [work.connection]
        assert work.repository(_FeatureRepositoryPort) is repository
        assert work.feature_repository is repository
        assert constructed_with == [work.connection]
        work.rollback()

    next_work = unit_of_work_module.PostgresUnitOfWork(_Database())
    with next_work:
        next_connection = next_work.connection
        next_repository = next_work.repository(_FeatureRepositoryPort)
        assert next_repository is not repository
        assert constructed_with == [first_connection, next_connection]
        next_work.rollback()
