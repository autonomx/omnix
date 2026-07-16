"""Transactional services for reusable RPG world and scenario resources."""
from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work

from .contracts import (
    CampaignWorldBinding,
    ScenarioProjectCreate,
    ScenarioRevisionDocument,
    WorldProjectCreate,
    WorldReleaseDocument,
    WorldRevisionDocument,
    canonical_content_hash,
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


def create_world_project(
    request: WorldProjectCreate,
    *,
    database: Any | None = None,
) -> dict[str, Any]:
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        world = work.world_scenarios.create_world(
            context,
            world_id=request.world_id,
            title=request.title,
            description=request.description,
            source_mode=request.source_mode,
            genre=request.genre,
            tone=request.tone,
            seed=request.seed,
            metadata=request.metadata,
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
    document = _ensure_hash(document, "release_hash")
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        stored = work.world_scenarios.publish_world_release(
            context,
            world_id=document.world_id,
            world_revision=document.world_revision,
            document=document.model_dump(mode="json"),
            release_hash=document.release_hash,
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
        scenario = work.world_scenarios.create_scenario(
            context,
            scenario_id=request.scenario_id,
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
        stored = work.world_scenarios.publish_scenario_revision(
            context,
            scenario_id=document.scenario_id,
            world_id=document.world_id,
            world_revision=document.world_revision,
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
        stored = work.world_scenarios.bind_campaign(
            context,
            campaign_id=binding.campaign_id,
            world_id=binding.world_id,
            world_revision=binding.world_revision,
            world_release=binding.world_release,
            scenario_id=binding.scenario_id,
            scenario_revision=binding.scenario_revision,
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


def load_published_resources(
    *,
    world_id: str,
    world_revision: int,
    world_release: int,
    scenario_id: str,
    scenario_revision: int,
    database: Any | None = None,
) -> tuple[WorldRevisionDocument, WorldReleaseDocument, ScenarioRevisionDocument]:
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        revision = work.world_scenarios.get_world_revision(
            context, world_id, world_revision
        )
        release = work.world_scenarios.get_world_release(
            context, world_id, world_revision, world_release
        )
        scenario = work.world_scenarios.get_scenario_revision(
            context, scenario_id, scenario_revision
        )
        work.rollback()
    if revision is None:
        raise KeyError(f"world_revision_not_found:{world_id}:{world_revision}")
    if release is None:
        raise KeyError(
            f"world_release_not_found:{world_id}:{world_revision}:{world_release}"
        )
    if scenario is None:
        raise KeyError(
            f"scenario_revision_not_found:{scenario_id}:{scenario_revision}"
        )
    return (
        WorldRevisionDocument.model_validate(revision["document"]),
        WorldReleaseDocument.model_validate(release["document"]),
        ScenarioRevisionDocument.model_validate(scenario["document"]),
    )
