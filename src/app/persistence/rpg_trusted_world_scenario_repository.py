"""Trusted-authorship persistence boundary for reusable RPG world topics."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Mapping

from app.rpg.worlds.generation_authorship import AuthorshipValidationError
from app.rpg.worlds.generation_authorship_runtime import (
    attach_human_authorship,
    generation_artifact,
    require_publishable_authorship,
)
from app.rpg.worlds.generation_test_mode import deterministic_world_forge_test_mode

from .rpg_repository import canonical_json
from .rpg_world_scenario_repository import PostgresRpgWorldScenarioRepository
from .tenant import TenantContext


def _hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(dict(value)).encode("utf-8")).hexdigest()


def _fixture_exempt(payload: Mapping[str, Any]) -> bool:
    provenance = payload.get("provenance")
    provenance = dict(provenance) if isinstance(provenance, Mapping) else {}
    exemption = provenance.get("test_authorship_exemption")
    exemption = dict(exemption) if isinstance(exemption, Mapping) else {}
    server_attested = (
        bool(exemption.get("server_attested"))
        and str(exemption.get("schema_version") or "")
        == "rpg_deterministic_fixture_exemption_v1"
        and str(exemption.get("recorded_provider_route") or "").strip().casefold()
        in {"deterministic", "offline", "reference-safe", "test"}
    )
    return server_attested or (
        deterministic_world_forge_test_mode()
        and (
            bool(provenance.get("deterministic_fixture_only"))
            or bool(exemption)
            or str(provenance.get("generator") or "").startswith("deterministic_")
        )
    )


class PostgresTrustedRpgWorldScenarioRepository(PostgresRpgWorldScenarioRepository):
    """Attach human origins and reject untrusted ready AI content before storage."""

    def _current_topic_content(
        self,
        context: TenantContext,
        world_id: str,
        topic_id: str,
    ) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT content_jsonb FROM omnix_rpg_world_topics "
            "WHERE workspace_id = %s AND world_id = %s AND topic_id = %s",
            (context.workspace_id, world_id, topic_id),
        ).fetchone()
        return dict(row[0]) if row is not None else {}

    def put_topic(
        self,
        context: TenantContext,
        *,
        world_id: str,
        topic_id: str,
        draft_revision: int,
        source: str,
        status: str,
        content: Mapping[str, Any],
        directives: Mapping[str, Any] | None = None,
        dependency_hashes: Mapping[str, str] | None = None,
        input_hash: str = "",
        content_hash: str = "",
        provenance: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(content)
        row_provenance = dict(provenance or {})
        embedded = dict(payload.get("provenance") or {})
        supplied_authorship = row_provenance.get("authorship")
        if supplied_authorship is not None and "authorship" not in embedded:
            embedded["authorship"] = supplied_authorship
        payload["provenance"] = embedded

        if source == "manual":
            try:
                require_publishable_authorship(payload)
                already_authored = True
            except AuthorshipValidationError:
                already_authored = False
            if not already_authored:
                prior = self._current_topic_content(context, world_id, topic_id)
                event_id = (
                    f"humanedit:{world_id}:{topic_id}:{draft_revision}:"
                    f"{datetime.now(timezone.utc).isoformat()}"
                )
                payload = attach_human_authorship(
                    payload,
                    event_id=event_id,
                    prior_candidate=prior,
                    edited_llm=bool(generation_artifact(prior)),
                )
                require_publishable_authorship(payload)
            content_hash = _hash(payload)
            embedded = dict(payload.get("provenance") or {})
            if "authorship" in embedded:
                row_provenance["authorship"] = embedded["authorship"]
        elif source == "ai" and status == "ready":
            if not _fixture_exempt(payload):
                artifact = generation_artifact(payload)
                require_publishable_authorship(payload, server_artifact=artifact)
            content_hash = _hash(payload)
            embedded = dict(payload.get("provenance") or {})
            if "authorship" in embedded:
                row_provenance["authorship"] = embedded["authorship"]

        return super().put_topic(
            context,
            world_id=world_id,
            topic_id=topic_id,
            draft_revision=draft_revision,
            source=source,
            status=status,
            content=payload,
            directives=directives,
            dependency_hashes=dependency_hashes,
            input_hash=input_hash,
            content_hash=content_hash or _hash(payload),
            provenance=row_provenance,
        )


__all__ = ["PostgresTrustedRpgWorldScenarioRepository"]
