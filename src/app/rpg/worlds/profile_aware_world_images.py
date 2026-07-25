"""Profile-aware image target planning layered over the legacy image service."""
from __future__ import annotations

from typing import Any, Mapping

from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work

from .generation_jobs import canonical_hash
from .library_service import read_world_detail
from .lifecycle_service import require_world_writable
from . import world_images as _base


def _record(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any, fallback: str = "") -> str:
    return str(value).strip() if value is not None and str(value).strip() else fallback


def _profile_domains(detail: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    world = _record(detail.get("world"))
    metadata = _record(world.get("metadata"))
    binding = _record(metadata.get("genre_profile_binding"))
    profile = _record(binding.get("profile"))
    return {
        _text(domain.get("domain_id")): domain
        for domain in (
            _record(value) for value in profile.get("domains") or ()
        )
        if _text(domain.get("domain_id"))
    }


def _presentation(domain: Mapping[str, Any]) -> dict[str, Any]:
    guidance = _record(domain.get("generation_guidance"))
    return _record(guidance.get("presentation"))


def _profile_targets(detail: Mapping[str, Any]) -> list[dict[str, Any]]:
    world = _record(detail.get("world"))
    domains = _profile_domains(detail)
    targets: list[dict[str, Any]] = []
    for topic_value in detail.get("topics") or ():
        topic = _record(topic_value)
        topic_id = _text(topic.get("topic_id"))
        domain = domains.get(topic_id)
        if not domain:
            continue
        presentation = _presentation(domain)
        role = _text(presentation.get("image_role"), "none")
        if role == "none":
            continue
        for entity in _base._entity_rows(_record(topic.get("content"))):
            entity_id = _text(entity.get("id") or entity.get("entity_id"))
            if not entity_id:
                continue
            entity_type = _text(entity.get("kind"), _text(domain.get("entity_kind"), topic_id.rstrip("s")))
            targets.append(
                {
                    "target_id": f"entity:{entity_id}:{role}",
                    "target_type": entity_type,
                    "entity_id": entity_id,
                    "role": role,
                    "source_content_hash": canonical_hash(entity),
                    "suggested_prompt": _base._prompt(
                        world=world,
                        target_type=entity_type,
                        role=role,
                        entity=entity,
                    ),
                    "metadata": {
                        "topic_id": topic_id,
                        "entity_name": _text(entity.get("name") or entity.get("title"), entity_id),
                        "profile_image_role": role,
                    },
                }
            )
            if topic_id == "places" or entity_type in {"place", "location", "settlement"}:
                targets.append(
                    {
                        "target_id": f"entity:{entity_id}:map",
                        "target_type": "map",
                        "entity_id": entity_id,
                        "role": "map",
                        "source_content_hash": canonical_hash({"entity": entity, "role": "location_map"}),
                        "suggested_prompt": _base._prompt(
                            world=world,
                            target_type="location map",
                            role="map",
                            entity=entity,
                        ),
                        "metadata": {
                            "topic_id": "map",
                            "map_level": "location",
                            "parent_target_id": "world:map",
                            "entity_name": _text(entity.get("name") or entity.get("title"), entity_id),
                        },
                    }
                )
    return targets


def _desired_targets(detail: Mapping[str, Any]) -> list[dict[str, Any]]:
    desired = list(_base._desired_targets(detail))
    by_id = {str(target["target_id"]): target for target in desired}
    for target in _profile_targets(detail):
        by_id.setdefault(str(target["target_id"]), target)
    return list(by_id.values())


def read_world_image_targets(
    world_id: str,
    *,
    database: Any | None = None,
) -> dict[str, Any]:
    detail = read_world_detail(world_id, database=database)
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        require_world_writable(work, context, world_id)
        _base._upsert_targets(work, context, world_id, _desired_targets(detail))
        _base._sync_jobs(work, context, world_id)
        targets = _base._list_targets(work, context, world_id)
        work.commit()
    return {"ok": True, "world": detail["world"], "targets": targets}


# The legacy generator resolves read_world_image_targets from its module globals.
# Install the profile-aware materializer once, then keep the proven generation and
# review implementations unchanged.
_base.read_world_image_targets = read_world_image_targets

generate_world_images = _base.generate_world_images
update_world_image_target = _base.update_world_image_target
approved_world_asset_bindings = _base.approved_world_asset_bindings

__all__ = [
    "approved_world_asset_bindings",
    "generate_world_images",
    "read_world_image_targets",
    "update_world_image_target",
]
