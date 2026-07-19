from __future__ import annotations

from app.assistant_memory.owner_defaults import (
    clear_default_memory_repository_factory,
    default_memory_service,
    install_default_memory_repository_factory,
    reset_default_memory_service,
)
from app.assistant_memory.owner_repository import OwnerAwareInMemoryMemoryRepository


def test_default_memory_service_does_not_cache_prebootstrap(monkeypatch) -> None:
    from app.persistence import runtime_install

    clear_default_memory_repository_factory()
    monkeypatch.setattr(runtime_install, "runtime_adapters_installed", lambda: False)

    first = default_memory_service()
    second = default_memory_service()

    assert first is not second
    assert isinstance(first.repository, OwnerAwareInMemoryMemoryRepository)
    assert isinstance(second.repository, OwnerAwareInMemoryMemoryRepository)


def test_installed_repository_factory_is_resident_and_resettable() -> None:
    calls: list[OwnerAwareInMemoryMemoryRepository] = []

    def factory() -> OwnerAwareInMemoryMemoryRepository:
        repository = OwnerAwareInMemoryMemoryRepository("factory:test")
        calls.append(repository)
        return repository

    clear_default_memory_repository_factory()
    install_default_memory_repository_factory(factory)
    try:
        first = default_memory_service()
        second = default_memory_service()
        assert first is second
        assert len(calls) == 1

        reset_default_memory_service()
        third = default_memory_service()
        assert third is not first
        assert len(calls) == 2
    finally:
        clear_default_memory_repository_factory()
