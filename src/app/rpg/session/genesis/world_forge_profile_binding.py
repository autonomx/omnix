"""Persist and restore the exact genre profile selected for a reusable world."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .world_forge_profile_generation import (
    ProfileResolution,
    normalize_genre_key,
    resolve_or_generate_genre_profile,
)
from .world_forge_profiles import (
    DomainDefinition,
    DomainTargetRange,
    FieldDefinition,
    GenreProfile,
    LaunchRequirements,
    RuntimeCapabilityDefaults,
)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> tuple[Any, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return ()


def _strings(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in _sequence(value) if str(item))


def _range(value: Any) -> tuple[int, int]:
    items = _sequence(value)
    if len(items) != 2:
        return (1, 1)
    return (max(1, int(items[0])), max(1, int(items[1])))


def genre_profile_from_payload(value: Mapping[str, Any]) -> GenreProfile:
    """Rebuild a validated immutable profile from persisted JSON metadata."""

    payload = _mapping(value)
    domains: list[DomainDefinition] = []
    for raw_domain in _sequence(payload.get("domains")):
        domain = _mapping(raw_domain)
        target = _mapping(domain.get("target_range"))
        fields = tuple(
            FieldDefinition(
                field_id=str(field.get("field_id") or ""),
                value_type=str(field.get("value_type") or "string"),  # type: ignore[arg-type]
                required=bool(field.get("required")),
                semantic_role=str(field.get("semantic_role") or ""),
                allowed_target_domains=_strings(field.get("allowed_target_domains")),
                enum_values=_strings(field.get("enum_values")),
                description=str(field.get("description") or ""),
            )
            for raw_field in _sequence(domain.get("fields"))
            if (field := _mapping(raw_field))
        )
        domains.append(
            DomainDefinition(
                domain_id=str(domain.get("domain_id") or ""),
                title=str(domain.get("title") or ""),
                entity_kind=str(domain.get("entity_kind") or ""),
                dependencies=_strings(domain.get("dependencies")),
                generator_role=str(domain.get("generator_role") or "world_forge"),
                required_before_launch=bool(domain.get("required_before_launch")),
                visibility_default=str(
                    domain.get("visibility_default") or "game_master_canon"
                ),
                fields=fields,
                target_range=DomainTargetRange(
                    quick=_range(target.get("quick")),
                    standard=_range(target.get("standard")),
                    epic=_range(target.get("epic")),
                ),
                semantic_roles=_strings(domain.get("semantic_roles")),
                category=str(domain.get("category") or "domain"),
                generation_guidance=_mapping(domain.get("generation_guidance")),
            )
        )
    launch = _mapping(payload.get("launch_requirements"))
    profile = GenreProfile(
        profile_id=str(payload.get("profile_id") or ""),
        version=int(payload.get("version") or 1),
        display_name=str(payload.get("display_name") or ""),
        domains=tuple(domains),
        aliases=_strings(payload.get("aliases")),
        parent_profile_ids=_strings(payload.get("parent_profile_ids")),
        modifier_ids=_strings(payload.get("modifier_ids")),
        genre_tags=_strings(payload.get("genre_tags")),
        launch_requirements=LaunchRequirements(
            required_domain_ids=_strings(launch.get("required_domain_ids")),
            required_semantic_roles=_strings(
                launch.get("required_semantic_roles")
            )
            or LaunchRequirements().required_semantic_roles,
        ),
        runtime_capability_defaults=RuntimeCapabilityDefaults(
            {
                str(key): bool(item)
                for key, item in _mapping(
                    payload.get("runtime_capability_defaults")
                ).items()
            }
        ),
        provenance=_mapping(payload.get("provenance")),
        scope=str(payload.get("scope") or "world_local"),  # type: ignore[arg-type]
    ).require_valid()
    expected_hash = str(payload.get("content_hash") or "")
    if expected_hash and expected_hash != profile.content_hash:
        raise ValueError("bound_genre_profile_hash_mismatch")
    return profile


def bind_world_genre_profile_metadata(
    metadata: Mapping[str, Any] | None,
    *,
    genre: str,
    description: str,
) -> dict[str, Any]:
    """Resolve once and persist the exact profile used before generation starts."""

    result = dict(metadata or {})
    resolution = resolve_or_generate_genre_profile(
        genre=genre,
        description=description,
        campaign_mode=str(
            result.get("campaign_mode") or "persistent_living_world"
        ),
    )
    result.update(
        {
            "resolved_genre_profile": resolution.profile.as_dict(),
            "resolved_profile_hash": resolution.profile.content_hash,
            "genre_profile_resolution_source": resolution.source,
            "genre_profile_id": resolution.profile.profile_id,
            "genre_profile_version": resolution.profile.version,
        }
    )
    return result


def resolve_bound_world_genre_profile(
    world: Mapping[str, Any],
) -> ProfileResolution:
    """Prefer the immutable world binding and fall back for older test worlds."""

    metadata = _mapping(world.get("metadata"))
    bound = metadata.get("resolved_genre_profile")
    if isinstance(bound, Mapping):
        profile = genre_profile_from_payload(bound)
        expected_hash = str(metadata.get("resolved_profile_hash") or "")
        if expected_hash and expected_hash != profile.content_hash:
            raise ValueError("world_genre_profile_binding_hash_mismatch")
        requested_genre = str(world.get("genre") or profile.display_name)
        return ProfileResolution(
            profile=profile,
            source="world_metadata_binding",
            requested_genre=requested_genre,
            normalized_genre=normalize_genre_key(requested_genre),
            generated=profile.scope == "world_local",
        )
    return resolve_or_generate_genre_profile(
        genre=str(world.get("genre") or "classic_fantasy"),
        description=str(world.get("description") or ""),
        campaign_mode=str(
            metadata.get("campaign_mode") or "persistent_living_world"
        ),
    )
