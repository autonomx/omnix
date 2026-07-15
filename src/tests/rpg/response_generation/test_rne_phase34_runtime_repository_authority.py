from __future__ import annotations

from app.rpg.narrative_repository import (
    PostgresNarrativeResponseRepositoryAdapter,
    build_production_narrative_repository,
    reset_narrative_repository_cache,
)
from app.rpg.narrative_engine.repository import InMemoryNarrativeResponseRepository


def test_installed_postgresql_runtime_selects_durable_narrative_repository(
    monkeypatch,
) -> None:
    monkeypatch.delenv("OMNIX_RPG_NARRATIVE_REPOSITORY", raising=False)
    monkeypatch.delenv("OMNIX_RPG_PERSISTENCE_MODE", raising=False)
    monkeypatch.setattr(
        "app.rpg.narrative_repository._runtime_postgresql_active",
        lambda: True,
    )
    reset_narrative_repository_cache()
    try:
        first = build_production_narrative_repository()
        second = build_production_narrative_repository()
        assert isinstance(first, PostgresNarrativeResponseRepositoryAdapter)
        assert first is second
    finally:
        reset_narrative_repository_cache()


def test_explicit_portable_mode_overrides_installed_runtime(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.rpg.narrative_repository._runtime_postgresql_active",
        lambda: True,
    )
    reset_narrative_repository_cache()
    try:
        repository = build_production_narrative_repository(
            environ={"OMNIX_RPG_NARRATIVE_REPOSITORY": "in_memory"}
        )
        assert isinstance(repository, InMemoryNarrativeResponseRepository)
    finally:
        reset_narrative_repository_cache()


def test_explicit_postgresql_mode_works_before_runtime_install(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.rpg.narrative_repository._runtime_postgresql_active",
        lambda: False,
    )
    reset_narrative_repository_cache()
    try:
        repository = build_production_narrative_repository(
            environ={"OMNIX_RPG_NARRATIVE_REPOSITORY": "postgresql"}
        )
        assert isinstance(repository, PostgresNarrativeResponseRepositoryAdapter)
    finally:
        reset_narrative_repository_cache()
