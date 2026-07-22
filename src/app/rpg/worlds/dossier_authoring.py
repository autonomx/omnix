"""Editorial-only authoring for rich reusable-world entity dossiers.

These operations deliberately preserve entity identity, mechanics, references, facts,
and relationships.  They update only short-form catalogue prose and the versioned
long-form dossier, so unrelated simulation canon does not become stale.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from typing import Any, Mapping

from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work
from app.rpg.session.genesis.world_forge_dossiers import (
    DOSSIER_SCHEMA_VERSION,
    compact_summary,
    project_entity_dossier,
    validate_entity_dossier,
)
from app.rpg.session.genesis.world_forge_generation import (
    GeneratedTopic,
    WorldForgeTopicGenerator,
)

from .entity_authoring import (
    _entity,
    _known_ids,
    _record_history,
    _topic_node,
    replace_entity_content,
    validate_entity_references,
)
from .generation_jobs import canonical_hash
from .topic_authoring import (
    _assert_writable_topic,
    _authoring,
    _latest_run,
    _record,
)


def _store_editorial_replacement(
    world_id: str,
    topic_id: str,
    entity_id: str,
    *,
    expected_draft_revision: int,
    expected_content_hash: str,
    short_summary: str,
    dossier: Mapping[str, Any],
    operation: str,
    metadata: Mapping[str, Any] | None = None,
    database: Any | None = None,
) -> dict[str, Any]:
    issues = validate_entity_dossier(dossier)
    if issues:
        raise ValueError("world_entity_dossier_invalid:" + ",".join(issues))
    summary = compact_summary(short_summary)
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        world, current = _assert_writable_topic(
            work,
            context,
            world_id=world_id,
            topic_id=topic_id,
            expected_draft_revision=expected_draft_revision,
            expected_content_hash=expected_content_hash,
        )
        before = _entity(_record(current.get("content")), entity_id)
        after = {
            **before,
            "id": entity_id,
            "short_summary": summary,
            "dossier": dict(dossier),
        }
        topic_rows = work.world_generation.list_topics(
            context,
            world_id=world_id,
            draft_revision=int(world["draft_revision"]),
        )
        validate_entity_references(
            after,
            _known_ids(topic_rows, world_id).union({entity_id}),
        )
        payload = replace_entity_content(
            _record(current.get("content")),
            entity_id,
            after,
        )
        content_hash = canonical_hash(payload)
        provenance = _record(current.get("provenance"))
        existing_authoring = _authoring(current)
        provenance["authoring"] = {
            **existing_authoring,
            "editorial_state": "edited",
            "entity_dossier_schema": DOSSIER_SCHEMA_VERSION,
            "last_entity_edit": {
                "entity_id": entity_id,
                "operation": operation,
                "editorial_only": True,
                "edited_at": datetime.now(timezone.utc).isoformat(),
            },
        }
        stored = work.world_scenarios.put_topic(
            context,
            world_id=world_id,
            topic_id=topic_id,
            draft_revision=int(world["draft_revision"]),
            source=str(current.get("source") or "ai"),
            status="ready",
            content=payload,
            directives=_record(current.get("directives")),
            dependency_hashes=_record(current.get("dependency_hashes")),
            input_hash=canonical_hash(
                {
                    "source": operation,
                    "entity_id": entity_id,
                    "short_summary": summary,
                    "dossier": dict(dossier),
                }
            ),
            content_hash=content_hash,
            provenance=provenance,
        )
        _record_history(
            work,
            context,
            world_id=world_id,
            topic_id=topic_id,
            entity_id=entity_id,
            operation=operation,
            before=before,
            after=after,
            topic_content_hash=content_hash,
            metadata={"editorial_only": True, **dict(metadata or {})},
        )
        work.commit()
    return {
        "ok": True,
        "topic": stored,
        "entity": after,
        "stale_topic_ids": [],
        "stale_entity_ids": [],
        "canonical_fields_preserved": True,
        "editorial_only": True,
    }


def update_world_entity_dossier(
    world_id: str,
    topic_id: str,
    entity_id: str,
    *,
    expected_draft_revision: int,
    expected_content_hash: str,
    short_summary: str,
    dossier: Mapping[str, Any],
    database: Any | None = None,
) -> dict[str, Any]:
    return _store_editorial_replacement(
        world_id,
        topic_id,
        entity_id,
        expected_draft_revision=expected_draft_revision,
        expected_content_hash=expected_content_hash,
        short_summary=short_summary,
        dossier=dossier,
        operation="manual_dossier_edit",
        database=database,
    )


def regenerate_world_entity_dossier(
    world_id: str,
    topic_id: str,
    entity_id: str,
    *,
    expected_draft_revision: int,
    expected_content_hash: str,
    directives: Mapping[str, Any] | None = None,
    generator: WorldForgeTopicGenerator | None = None,
    database: Any | None = None,
) -> dict[str, Any]:
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        world, current = _assert_writable_topic(
            work,
            context,
            world_id=world_id,
            topic_id=topic_id,
            expected_draft_revision=expected_draft_revision,
            expected_content_hash=expected_content_hash,
        )
        before = _entity(_record(current.get("content")), entity_id)
        run = _latest_run(work, context, world_id)
        node = _topic_node(world, run, topic_id)
        rows = work.world_generation.list_topics(
            context,
            world_id=world_id,
            draft_revision=int(world["draft_revision"]),
        )
        row_map = {str(row.get("topic_id") or ""): row for row in rows}
        dependencies = {
            dependency_id: GeneratedTopic.from_dict(
                _record(row_map[dependency_id].get("content"))
            )
            for dependency_id in node.dependencies
            if dependency_id in row_map
        }
        work.rollback()

    selected_generator = generator
    if selected_generator is None:
        from app.rpg_world_forge_provider import build_production_world_forge_generator

        selected_generator = build_production_world_forge_generator()
    node = replace(
        node,
        target_count=1,
        metadata={
            **dict(node.metadata),
            "entity_dossier_regeneration": {
                "entity_id": entity_id,
                "entity_name": str(before.get("name") or ""),
                "editorial_only": True,
                "preserve_all_other_fields": True,
                "directives": dict(directives or {}),
            },
        },
    )
    generated = selected_generator.generate(
        node,
        seed=int(world.get("seed") or 0),
        campaign_context={
            "campaign_template": _record(world.get("metadata")).get(
                "campaign_template"
            )
            or "classic_fantasy",
            "genre": str(world.get("genre") or "classic_fantasy"),
            "tone": str(world.get("tone") or "heroic adventure"),
            "custom_directives": [
                json.dumps(dict(directives or {}), sort_keys=True)
            ],
            "entity_dossier_regeneration": {
                "entity_id": entity_id,
                "current_canonical_entity": before,
                "allowed_output_fields": ["short_summary", "dossier"],
            },
        },
        dependency_topics=dependencies,
    )
    if not generated.entities:
        raise ValueError(
            f"world_entity_dossier_regeneration_empty:{topic_id}:{entity_id}"
        )
    candidate = next(
        (
            dict(row)
            for row in generated.entities
            if str(row.get("id") or row.get("entity_id") or "") == entity_id
        ),
        dict(generated.entities[0]),
    )
    short_summary, dossier = project_entity_dossier(
        candidate,
        card_type=topic_id,
        content=generated.as_dict(),
        entity_id=entity_id,
    )
    return _store_editorial_replacement(
        world_id,
        topic_id,
        entity_id,
        expected_draft_revision=expected_draft_revision,
        expected_content_hash=expected_content_hash,
        short_summary=short_summary,
        dossier=dossier,
        operation="regenerate_dossier",
        metadata={
            "directives": dict(directives or {}),
            "generation": dict(generated.provenance),
        },
        database=database,
    )
