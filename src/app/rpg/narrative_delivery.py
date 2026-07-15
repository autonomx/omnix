"""Production adapters for durable canonical narrative delivery."""
from __future__ import annotations

import os
from functools import lru_cache
from threading import RLock
from typing import Any, Callable, Mapping

from app.persistence.database import PostgresDatabase, default_database
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.tenant import TenantContext
from app.persistence.unit_of_work import unit_of_work
from app.rpg.narrative_engine.authority import DeliveryMode
from app.rpg.narrative_engine.delivery import (
    InMemoryNarrativeDeliveryRepository,
    NarrativeDeliveryAdvance,
    NarrativeDeliveryCoordinator,
    NarrativeDeliveryRecord,
    NarrativeDeliveryRepository,
)
from app.rpg.narrative_engine.serialization import canonical_response_from_dict
from app.rpg.narrative_repository import build_production_narrative_repository


class PostgresNarrativeDeliveryRepositoryAdapter:
    """Adapt tenant-scoped PostgreSQL delivery cursors to the engine port."""

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

    def open(
        self,
        *,
        response_id: str,
        semantic_hash: str,
        mode: DeliveryMode,
        block_ids: tuple[str, ...],
        metadata: Mapping[str, Any] | None = None,
    ) -> NarrativeDeliveryRecord:
        with self._unit_of_work_factory(self.database) as work:
            record = work.narrative_deliveries.open(
                self._context(),
                response_id=response_id,
                semantic_hash=semantic_hash,
                mode=mode,
                block_ids=block_ids,
                metadata=metadata,
            )
            work.commit()
            return record

    def get(self, response_id: str) -> NarrativeDeliveryRecord | None:
        with self._unit_of_work_factory(self.database) as work:
            record = work.narrative_deliveries.get(self._context(), response_id)
            work.rollback()
            return record

    def advance(
        self,
        response_id: str,
        *,
        expected_semantic_hash: str,
    ) -> NarrativeDeliveryAdvance:
        with self._unit_of_work_factory(self.database) as work:
            advance = work.narrative_deliveries.advance(
                self._context(),
                response_id,
                expected_semantic_hash=expected_semantic_hash,
            )
            work.commit()
            return advance

    def cancel(
        self,
        response_id: str,
        *,
        expected_semantic_hash: str,
        reason: str,
    ) -> NarrativeDeliveryRecord:
        with self._unit_of_work_factory(self.database) as work:
            record = work.narrative_deliveries.cancel(
                self._context(),
                response_id,
                expected_semantic_hash=expected_semantic_hash,
                reason=reason,
            )
            work.commit()
            return record


def _runtime_postgresql_active() -> bool:
    try:
        from app.persistence.runtime_install import runtime_adapters_installed

        return runtime_adapters_installed()
    except Exception:
        return False


def _delivery_repository_mode(environ: Mapping[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    explicit = str(
        env.get("OMNIX_RPG_NARRATIVE_DELIVERY_REPOSITORY")
        or env.get("OMNIX_RPG_NARRATIVE_REPOSITORY")
        or env.get("OMNIX_RPG_PERSISTENCE_MODE")
        or ""
    ).strip().casefold()
    if explicit:
        return explicit
    if environ is None and _runtime_postgresql_active():
        return "postgresql"
    return "in_memory"


@lru_cache(maxsize=4)
def _cached_delivery_repository(mode: str) -> NarrativeDeliveryRepository:
    if mode in {"postgres", "postgresql", "production_authoritative"}:
        return PostgresNarrativeDeliveryRepositoryAdapter()
    if mode in {"in_memory", "memory", "test", "development_portable", "portable"}:
        return InMemoryNarrativeDeliveryRepository()
    raise ValueError(f"unknown RPG narrative delivery repository mode: {mode}")


def build_production_narrative_delivery_repository(
    *,
    environ: Mapping[str, str] | None = None,
) -> NarrativeDeliveryRepository:
    return _cached_delivery_repository(_delivery_repository_mode(environ))


def reset_narrative_delivery_repository_cache() -> None:
    _cached_delivery_repository.cache_clear()


def prepare_canonical_result_delivery(
    result: dict[str, Any],
    mode: DeliveryMode,
    *,
    response_repository: Any | None = None,
    delivery_repository: NarrativeDeliveryRepository | None = None,
) -> dict[str, Any]:
    """Persist one approved response and open its delivery cursor without rewriting it."""

    raw = result.get("canonical_narrative_response")
    if not isinstance(raw, Mapping):
        return result
    response = canonical_response_from_dict(raw)
    response_repo = response_repository or build_production_narrative_repository()
    delivery_repo = delivery_repository or build_production_narrative_delivery_repository()
    persisted = response_repo.save(response)
    projected = NarrativeDeliveryCoordinator().open(persisted, mode, delivery_repo)
    record = delivery_repo.get(projected.response_id)
    payload = projected.as_dict()
    result["canonical_narrative_response"] = payload
    result["narrative_delivery_state"] = record.as_dict() if record is not None else {}
    result["narrative_delivery_mode"] = mode.value
    result["narrative_delivery_response_id"] = projected.response_id
    result["narrative_delivery_semantic_hash"] = projected.semantic_hash
    nested = result.get("result")
    if isinstance(nested, dict) and isinstance(
        nested.get("canonical_narrative_response"), Mapping
    ):
        nested["canonical_narrative_response"] = payload
        nested["narrative_delivery_state"] = result["narrative_delivery_state"]
    return result


def deferred_public_turn_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Hide deferred prose until ordered blocks are published by the stream route."""

    raw = payload.get("canonical_narrative_response")
    if not isinstance(raw, Mapping):
        return payload
    delivery = raw.get("delivery") if isinstance(raw.get("delivery"), Mapping) else {}
    if str(delivery.get("mode") or "") != DeliveryMode.DEFERRED.value:
        return payload
    if str(delivery.get("status") or "") == "complete":
        return payload

    response_id = str(raw.get("response_id") or "")
    semantic_hash = str(raw.get("content_hash") or "")
    block_headers = [
        {
            "block_id": str(block.get("block_id") or ""),
            "sequence": int(block.get("sequence") or 0),
            "kind": str(block.get("kind") or "narration"),
            "purpose": str(block.get("purpose") or "continuation"),
            "speaker_id": block.get("speaker_id"),
        }
        for block in raw.get("blocks") or ()
        if isinstance(block, Mapping)
    ]
    envelope = {
        "schema_version": raw.get("schema_version"),
        "response_id": response_id,
        "request_id": raw.get("request_id"),
        "turn_id": raw.get("turn_id"),
        "campaign_id": raw.get("campaign_id"),
        "revision": raw.get("revision"),
        "content_hash": semantic_hash,
        "semantic_hash": semantic_hash,
        "delivery": dict(delivery),
        "blocks": block_headers,
        "prose_deferred": True,
    }
    pending_visible = {
        "plain_text": "",
        "status": "deferred",
        "response_id": response_id,
        "semantic_hash": semantic_hash,
    }
    payload["visible_response"] = pending_visible
    payload["response"] = ""
    payload["content"] = ""
    compact = payload.get("result")
    if isinstance(compact, dict):
        compact["visible_response"] = pending_visible
        compact["narration_status"] = "deferred"
    payload["canonical_narrative_response"] = envelope
    payload.pop("narrative_projections", None)
    payload["deferred_narrative_delivery"] = {
        "response_id": response_id,
        "semantic_hash": semantic_hash,
        "status": str(delivery.get("status") or "pending"),
        "next_index": int(
            (delivery.get("metadata") or {}).get("next_index")
            if isinstance(delivery.get("metadata"), Mapping)
            else 0
        ),
        "stream_path": f"/api/rpg/narrative-responses/{response_id}/stream",
        "status_path": f"/api/rpg/narrative-responses/{response_id}/delivery",
        "cancel_path": f"/api/rpg/narrative-responses/{response_id}/cancel",
    }
    return payload
