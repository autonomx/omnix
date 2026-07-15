"""Production persistence adapters for canonical RPG narrative responses."""
from __future__ import annotations

import os
from functools import lru_cache
from threading import RLock
from typing import Any, Callable

from app.persistence.database import PostgresDatabase, default_database
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.rpg_narrative_response_repository import (
    NarrativeResponsePersistenceConflict,
)
from app.persistence.tenant import TenantContext
from app.persistence.unit_of_work import unit_of_work
from app.rpg.narrative_engine import CanonicalNarrativeResponse
from app.rpg.narrative_engine.repository import (
    InMemoryNarrativeResponseRepository,
    NarrativeResponseConflict,
    NarrativeResponseRepository,
)


class PostgresNarrativeResponseRepositoryAdapter:
    """Adapt tenant-scoped PostgreSQL persistence to the engine repository port."""

    def __init__(
        self,
        database: PostgresDatabase | None = None,
        *,
        context_provider: Callable[[PostgresDatabase], TenantContext] = bootstrap_local_tenant,
        unit_of_work_factory: Callable[..., Any] = unit_of_work,
    ) -> None:
        self.database = database or default_database()
        self._context_provider = context_provider
        self._unit_of_work_factory = unit_of_work_factory
        self._context_lock = RLock()
        self._tenant_context: TenantContext | None = None

    def _context(self) -> TenantContext:
        with self._context_lock:
            if self._tenant_context is None:
                self._tenant_context = self._context_provider(self.database)
            return self._tenant_context

    def save(
        self,
        response: CanonicalNarrativeResponse,
    ) -> CanonicalNarrativeResponse:
        with self._unit_of_work_factory(self.database) as work:
            try:
                saved = work.narrative_responses.save(
                    self._context(),
                    response.with_content_hash(),
                )
            except NarrativeResponsePersistenceConflict as exc:
                work.rollback()
                raise NarrativeResponseConflict(str(exc)) from exc
            work.commit()
            return saved

    def get(self, response_id: str) -> CanonicalNarrativeResponse | None:
        with self._unit_of_work_factory(self.database) as work:
            value = work.narrative_responses.get(self._context(), response_id)
            work.rollback()
            return value

    def get_for_turn(
        self,
        campaign_id: str,
        turn_id: str,
    ) -> CanonicalNarrativeResponse | None:
        with self._unit_of_work_factory(self.database) as work:
            value = work.narrative_responses.get_for_turn(
                self._context(),
                campaign_id,
                turn_id,
            )
            work.rollback()
            return value

    def list_campaign(
        self,
        campaign_id: str,
        *,
        limit: int = 500,
    ) -> tuple[CanonicalNarrativeResponse, ...]:
        with self._unit_of_work_factory(self.database) as work:
            values = work.narrative_responses.list_campaign(
                self._context(),
                campaign_id,
                limit=limit,
            )
            work.rollback()
            return values


def _runtime_postgresql_active() -> bool:
    try:
        from app.persistence.runtime_install import runtime_adapters_installed

        return runtime_adapters_installed()
    except Exception:
        return False


def _repository_mode(environ: dict[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    explicit = str(
        env.get("OMNIX_RPG_NARRATIVE_REPOSITORY")
        or env.get("OMNIX_RPG_PERSISTENCE_MODE")
        or ""
    ).strip().casefold()
    if explicit:
        return explicit
    if environ is None and _runtime_postgresql_active():
        return "postgresql"
    return "in_memory"


@lru_cache(maxsize=4)
def _cached_repository(mode: str) -> NarrativeResponseRepository:
    if mode in {"postgres", "postgresql", "production_authoritative"}:
        return PostgresNarrativeResponseRepositoryAdapter()
    if mode in {"in_memory", "memory", "test", "development_portable", "portable"}:
        return InMemoryNarrativeResponseRepository()
    raise ValueError(f"unknown RPG narrative repository mode: {mode}")


def build_production_narrative_repository(
    *,
    environ: dict[str, str] | None = None,
) -> NarrativeResponseRepository:
    """Resolve one shared repository; installed production runtime implies PostgreSQL."""

    return _cached_repository(_repository_mode(environ))


def reset_narrative_repository_cache() -> None:
    _cached_repository.cache_clear()
