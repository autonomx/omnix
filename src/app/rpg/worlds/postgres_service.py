"""Transactional services for reusable RPG world and scenario resources."""
from __future__ import annotations

import re
from typing import Any, TypeVar
from uuid import uuid4

from pydantic import BaseModel

from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work
from app.rpg.map_grid_contracts import GridMapDefinition
from app.rpg.session.genesis.world_forge_profile_binding import (
    bind_world_genre_profile_metadata,
)

from .contracts import (
    CampaignWorldBinding,
    ScenarioProjectCreate,
    ScenarioRevisionDocument,
    WorldProjectCreate,
    WorldReleaseDocument,
    WorldRevisionDocument,
    canonical_content_hash,
)
from .lifecycle_service import require_scenario_writable, require_world_writable
from .semantic_validation import (
    WorldSemanticError,
    certify_world_release,
    validate_release_bindings,
    validate_scenario_against_release,
)

_HashedContract = TypeVar("_HashedContract", bound=BaseModel)


def _ensure_hash(document: _HashedContract, field: str) -> _HashedContract:
    current = str(getattr(document, field, "") or "")
    if current:
        return document
    payload = document.model_dump(mode="json")
    payload[field] = ""
    payload[field] = canonical_content_hash(payload)
    return type(document).model_validate(payload)


def _resource_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().casefold()).strip("-")
    return (slug or "untitled")[:48]


def _allocate_resource_id(
    work: Any,
    context: Any,
    *,
    prefix: str,
    title: str,
    exists_sql: str,
) -> str:
    """Allocate a friendly, collision-safe technical id inside the write transaction."""

    slug = _resource_slug(title)
    for _ in range(16):
        candidate = f"{prefix}:{slug}:{uuid4().hex[:12]}"
        existing = work.connection.execute(
            exists_sql,
            (context.workspace_id, candidate),
        ).fetchone()
        if existing is None:
            return candidate
    raise RuntimeError(f"{prefix}_id_allocation_exhausted")


def _definitions_from_work(
    work: Any,
    context: Any,
    release: WorldReleaseDocument,
) -> dict[str, GridMapDefinition]:
    definitions: dict[str, GridMapDefinition] = {}
    for binding in release.map_bindings:
        row = work.map_instances.get_definition(
            context,
            binding.map_id,
            binding.definition_revision,
        )
        if row is None:
            continue
        definitions[binding.map_id] = GridMapDefinition.model_validate(row["document"])
    return definitions


def _world_revision_from_work(
    work: Any,
    context: Any,
    world_id: str,
    revision: int,
) -> WorldRevisionDocument:
    row = work.world_scenarios.get_world_revision(context, world_id, revision)
    if row is None:
        raise KeyError(f"world_revision_not_found:{world_id}:{revision}")
    return WorldRevisionDocument.model_validate(row["document"])


def create_world_project(
    request: WorldProjectCreate,
    *,
    database: Any | None = None,
) -> dict[str, Any]:
    metadata = bind_world_genre_profile_metadata(
        request.metadata,
        genre=request.genre,
        description=request.description,
    )
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        world_id = str(request.world_id or "").strip()
        if world_id:
            if work.world_scenarios.get_world(context, world_id) is not None:
                raise ValueError(f"world_already_exists:{world_id}")
        else:
            world_id = _allocate_resource_id(
                work,
                context,
                prefix="world",
                title=request.title,
                exists_sql=(
                    "SELECT 1 FROM omnix_rpg_worlds "
                    "WHERE workspace_id = %s AND id = %s"
                ),
            )
        world = work.world_scenarios.create_world(
            context,
            world_id=world_id,
            title=request.title,
            description=request.description,
            source_mode=request.source_mode,
            genre=request.genre,
            tone=request.tone,
            seed=request.seed,
            metadata=metadata,
        )
        work.commit()
    return world


def list_world_projects(
    *,
    database: Any | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        worlds = work.world_scenarios.list_worlds(context, limit=limit)
        work.rollback()
    return worlds


def publish_world_revision(
    document: WorldRevisionDocument,
    *,
    expected_revision: int,
    database: Any | None = None,
) -> dict[str, Any]:
    document = _ensure_hash(document, "content_hash")
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        require_world_writable(work, context, document.world_id)
        stored = work.world_scenarios.publish_world_revision(
            context,
            world_id=document.world_id,
            document=document.model_dump(mode="json"),
            content_hash=document.content_hash,
            expected_revision=expected_revision,
        )
        work.commit()
    return stored


def publish_world_release(
    document: WorldReleaseDocument,
    *,
    database: Any | None = None,
) -> dict[str, Any]:
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        require_world_writable(work, context, document.world_id)
        world_revision = _world_revision_from_work(
            work,
            context,
            document.world_id,
            document.world_revision,
        )
        next_row = work.connection.execute(
            "SELECT COALESCE(MAX(release), 0) + 1 FROM omnix_rpg_world_releases "
            "WHERE workspace_id = %s AND world_id = %s AND world_revision = %s",
            (context.workspace_id, document.world_id, document.world_revision),
        ).fetchone()
        next_release = int(next_row[0])
        if document.release != next_release:
            raise WorldSemanticError(
                "world_release_sequence_mismatch",
                f"expected={next_release}:received={document.release}",
            )
        definitions = _definitions_from_work(work, context, document)
        certified = certify_world_release(world_revision, document, definitions)
        stored = work.world_scenarios.publish_world_release(
            context,
            world_id=certified.world_id,
            world_revision=certified.world_revision,
            document=certified.model_dump(mode="json"),
            release_hash=certified.release_hash,
        )
        work.commit()
    return stored


def create_scenario_project(
    request: ScenarioProjectCreate,
    *,
    database: Any | None = None,
) -> dict[str, Any]:
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        require_world_writable(work, context, request.world_id)
        scenario_id = str(request.scenario_id or "").strip()
        if scenario_id:
            existing = work.connection.execute(
                "SELECT 1 FROM omnix_rpg_scenarios "
                "WHERE workspace_id = %s AND id = %s",
                (context.workspace_id, scenario_id),
            ).fetchone()
            if existing is not None:
                raise ValueError(f"scenario_already_exists:{scenario_id}")
        else:
            scenario_id = _allocate_resource_id(
                work,
                context,
                prefix="scenario",
                title=request.title,
                exists_sql=(
                    "SELECT 1 FROM omnix_rpg_scenarios "
                    "WHERE workspace_id = %s AND id = %s"
                ),
            )
        scenario = work.world_scenarios.create_scenario(
            context,
            scenario_id=scenario_id,
            world_id=request.world_id,
            title=request.title,
            description=request.description,
            metadata=request.metadata,
        )
        work.commit()
    return scenario


def publish_scenario_revision(
    document: ScenarioRevisionDocument,
    *,
    database: Any | None = None,
) -> dict[str, Any]:
    document = _ensure_hash(document, "content_hash")
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        require_scenario_writable(work, context, document.scenario_id)
        next_row = work.connection.execute(
            "SELECT COALESCE(MAX(revision), 0) + 1 FROM omnix_rpg_scenario_revisions "
            "WHERE workspace_id = %s AND scenario_id = %s",
            (context.workspace_id, document.scenario_id),
        ).fetchone()
        next_revision = int(next_row[0])
        if document.revision != next_revision:
            raise WorldSemanticError(
                "scenario_revision_sequence_mismatch",
                f"expected={next_revision}:received={document.revision}",
            )
        stored = work.world_scenarios.publish_scenario_revision(
            context,
            scenario_id=document.scenario_id,
            document=document.model_dump(mode="json"),
            content_hash=document.content_hash,
        )
        work.commit()
    return stored


def bind_campaign_world(
    binding: CampaignWorldBinding,
    *,
    database: Any | None = None,
) -> dict[str, Any]:
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        stored = work.world_scenarios.bind_campaign_world(
            context,
            campaign_id=binding.campaign_id,
            binding=binding.model_dump(mode="json"),
        )
        work.commit()
    return stored


def read_campaign_world_binding(
    campaign_id: str,
    *,
    database: Any | None = None,
) -> dict[str, Any] | None:
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        binding = work.world_scenarios.get_campaign_binding(context, campaign_id)
        work.rollback()
    return binding
