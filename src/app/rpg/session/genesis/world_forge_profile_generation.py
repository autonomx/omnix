"""Genre profile registry, resolution, and validated world-local generation."""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Mapping, Protocol

from .world_forge_profiles import (
    DomainDefinition,
    DomainTargetRange,
    FieldDefinition,
    GenreProfile,
    LaunchRequirements,
    RuntimeCapabilityDefaults,
)


def normalize_genre_key(value: str) -> str:
    return "_".join(re.findall(r"[a-z0-9]+", str(value or "").casefold())) or "unknown"


class GenreProfileGenerator(Protocol):
    def generate_profile(
        self,
        *,
        genre: str,
        description: str,
        campaign_mode: str,
    ) -> GenreProfile: ...


@dataclass(frozen=True)
class ProfileResolution:
    profile: GenreProfile
    source: str
    requested_genre: str
    normalized_genre: str
    generated: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile.as_dict(),
            "source": self.source,
            "requested_genre": self.requested_genre,
            "normalized_genre": self.normalized_genre,
            "generated": self.generated,
        }


class GenreProfileRegistry:
    def __init__(self, profiles: tuple[GenreProfile, ...] = ()) -> None:
        self._profiles: dict[str, GenreProfile] = {}
        self._aliases: dict[str, str] = {}
        for profile in profiles:
            self.register(profile)

    def register(self, profile: GenreProfile) -> None:
        profile.require_valid()
        self._profiles[profile.profile_id] = profile
        for value in (profile.profile_id, profile.display_name, *profile.aliases):
            self._aliases[normalize_genre_key(value)] = profile.profile_id

    def resolve(self, genre: str) -> GenreProfile | None:
        profile_id = self._aliases.get(normalize_genre_key(genre))
        return self._profiles.get(profile_id or "")

    def profiles(self) -> tuple[GenreProfile, ...]:
        return tuple(self._profiles[key] for key in sorted(self._profiles))


def _field(
    field_id: str,
    value_type: str = "string",
    *,
    required: bool = False,
    targets: tuple[str, ...] = (),
    semantic_role: str = "",
) -> FieldDefinition:
    return FieldDefinition(
        field_id=field_id,
        value_type=value_type,  # type: ignore[arg-type]
        required=required,
        allowed_target_domains=targets,
        semantic_role=semantic_role,
    )


def _core_domains() -> tuple[DomainDefinition, ...]:
    return (
        DomainDefinition(
            "setting_rules",
            "Setting Rules",
            "setting_rule",
            required_before_launch=True,
            semantic_roles=("starting_context",),
            fields=(
                _field("name", required=True),
                _field("rule", required=True),
                _field("observable_consequences", "structured_object", required=True),
            ),
        ),
        DomainDefinition(
            "places",
            "Places and Containers",
            "place",
            dependencies=("setting_rules",),
            required_before_launch=True,
            semantic_roles=("starting_context",),
            fields=(
                _field("name", required=True),
                _field("parent_place_id", "entity_ref", targets=("places",)),
                _field("access_routes", "structured_object", required=True),
                _field("current_pressure", required=True),
                _field("observable_evidence", "structured_object", required=True),
            ),
            target_range=DomainTargetRange((3, 5), (7, 10), (14, 22)),
        ),
        DomainDefinition(
            "groups",
            "Groups and Institutions",
            "group",
            dependencies=("setting_rules", "places"),
            required_before_launch=True,
            semantic_roles=("initial_conflict",),
            fields=(
                _field("name", required=True),
                _field("controlled_place_ids", "entity_ref_list", targets=("places",)),
                _field("resources", "structured_object", required=True),
                _field("dependencies", "structured_object", required=True),
                _field("internal_divisions", "structured_object", required=True),
                _field("current_objective", required=True),
                _field("next_action", required=True),
                _field("failure_response", required=True),
                _field("observable_signs", "structured_object", required=True),
            ),
            target_range=DomainTargetRange((3, 4), (5, 8), (9, 14)),
        ),
        DomainDefinition(
            "actors",
            "Actors",
            "actor",
            dependencies=("groups", "places"),
            required_before_launch=True,
            semantic_roles=("initial_actors",),
            fields=(
                _field("name", required=True),
                _field("location_id", "entity_ref", required=True, targets=("places",)),
                _field("group_ids", "entity_ref_list", targets=("groups",)),
                _field("goal", required=True),
                _field("dependency", required=True),
                _field("current_pressure", required=True),
                _field("next_action", required=True),
                _field("reaction_conditions", "structured_object", required=True),
                _field("knowledge_limits", "structured_object", required=True),
            ),
            target_range=DomainTargetRange((4, 6), (8, 12), (15, 25)),
        ),
        DomainDefinition(
            "pressures",
            "Current Pressures",
            "pressure",
            dependencies=("groups", "actors", "places"),
            required_before_launch=True,
            semantic_roles=("initial_conflict",),
            fields=(
                _field("name", required=True),
                _field("actor_ids", "entity_ref_list", targets=("actors",)),
                _field("group_ids", "entity_ref_list", targets=("groups",)),
                _field("place_ids", "entity_ref_list", targets=("places",)),
                _field("current_state", required=True),
                _field("next_tick_change", required=True),
                _field("escalation_condition", required=True),
                _field("observable_evidence", "structured_object", required=True),
            ),
            target_range=DomainTargetRange((3, 4), (5, 8), (9, 14)),
        ),
        DomainDefinition(
            "opening_threads",
            "Opening Threads",
            "opening_thread",
            dependencies=("pressures", "actors", "places", "groups"),
            required_before_launch=True,
            fields=(
                _field("name", required=True),
                _field("actor_ids", "entity_ref_list", targets=("actors",)),
                _field("place_ids", "entity_ref_list", targets=("places",)),
                _field("pressure_ids", "entity_ref_list", targets=("pressures",)),
                _field("initial_evidence", "structured_object", required=True),
                _field("player_choices", "structured_object", required=True),
                _field("aftermath", "structured_object", required=True),
            ),
            target_range=DomainTargetRange((2, 3), (3, 5), (5, 8)),
        ),
    )


def _profile(
    profile_id: str,
    display_name: str,
    *,
    aliases: tuple[str, ...],
    extra_domains: tuple[DomainDefinition, ...] = (),
    tags: tuple[str, ...] = (),
    capability_defaults: Mapping[str, bool] | None = None,
) -> GenreProfile:
    return GenreProfile(
        profile_id=profile_id,
        version=1,
        display_name=display_name,
        aliases=aliases,
        domains=(*_core_domains(), *extra_domains),
        genre_tags=tags,
        launch_requirements=LaunchRequirements(
            required_domain_ids=(
                "setting_rules",
                "places",
                "groups",
                "actors",
                "pressures",
                "opening_threads",
            ),
        ),
        runtime_capability_defaults=RuntimeCapabilityDefaults(
            dict(capability_defaults or {})
        ),
        provenance={"source": "built_in_profile_v1"},
        scope="built_in",
    ).require_valid()


def _post_apocalyptic_profile() -> GenreProfile:
    extras = (
        DomainDefinition(
            "survival_resources",
            "Survival Resources",
            "resource_system",
            dependencies=("places", "groups"),
            fields=(
                _field("name", required=True),
                _field("source_place_ids", "entity_ref_list", targets=("places",)),
                _field("controller_group_ids", "entity_ref_list", targets=("groups",)),
                _field("scarcity", required=True),
                _field("failure_effect", required=True),
            ),
        ),
        DomainDefinition(
            "ruins",
            "Ruins and Pre-collapse Remains",
            "ruin",
            dependencies=("places", "setting_rules"),
            fields=(
                _field("name", required=True),
                _field("place_id", "entity_ref", required=True, targets=("places",)),
                _field("former_purpose", required=True),
                _field("current_hazard", required=True),
                _field("recoverable_evidence", "structured_object", required=True),
            ),
        ),
        DomainDefinition(
            "mutations",
            "Mutations and Adaptations",
            "mutation",
            dependencies=("setting_rules",),
            fields=(
                _field("name", required=True),
                _field("cause", required=True),
                _field("effects", "structured_object", required=True),
                _field("limitations", "structured_object", required=True),
            ),
        ),
    )
    return _profile(
        "post_apocalyptic",
        "Post-apocalyptic",
        aliases=("post apocalypse", "wasteland", "nuclear wasteland", "fallout style"),
        extra_domains=extras,
        tags=("scarcity", "survival", "collapse"),
        capability_defaults={"scarcity": True, "resource_simulation": True},
    )


def _cyberpunk_profile() -> GenreProfile:
    extras = (
        DomainDefinition(
            "networks",
            "Networks and Digital Spaces",
            "network",
            dependencies=("groups", "places"),
            fields=(
                _field("name", required=True),
                _field("controller_group_ids", "entity_ref_list", targets=("groups",)),
                _field("access_conditions", "structured_object", required=True),
                _field("security_pressure", required=True),
            ),
        ),
        DomainDefinition(
            "augmentations",
            "Augmentations",
            "augmentation",
            dependencies=("setting_rules", "groups"),
            fields=(
                _field("name", required=True),
                _field("capability", required=True),
                _field("cost", required=True),
                _field("dependency", required=True),
                _field("failure_mode", required=True),
            ),
        ),
    )
    return _profile(
        "cyberpunk",
        "Cyberpunk",
        aliases=("cyber punk", "corporate dystopia", "high tech low life"),
        extra_domains=extras,
        tags=("corporations", "augmentation", "networks"),
        capability_defaults={"digital_spaces": True, "economy": True},
    )


def _fantasy_profile() -> GenreProfile:
    extras = (
        DomainDefinition(
            "supernatural_systems",
            "Supernatural Systems",
            "supernatural_system",
            dependencies=("setting_rules", "groups"),
            fields=(
                _field("name", required=True),
                _field("source", required=True),
                _field("costs", "structured_object", required=True),
                _field("limits", "structured_object", required=True),
                _field("institutions", "entity_ref_list", targets=("groups",)),
            ),
        ),
    )
    return _profile(
        "classic_fantasy",
        "Classic fantasy",
        aliases=("fantasy", "high fantasy", "medieval fantasy"),
        extra_domains=extras,
        tags=("fantasy", "supernatural"),
        capability_defaults={"supernatural_rules": True},
    )


def default_profile_registry() -> GenreProfileRegistry:
    return GenreProfileRegistry(
        (_fantasy_profile(), _post_apocalyptic_profile(), _cyberpunk_profile())
    )


class HeuristicWorldLocalProfileGenerator:
    """Safe fallback when no model-backed profile generator is configured."""

    def generate_profile(
        self,
        *,
        genre: str,
        description: str,
        campaign_mode: str,
    ) -> GenreProfile:
        normalized = normalize_genre_key(genre)
        concept_domain = DomainDefinition(
            "genre_elements",
            f"{genre.strip() or 'Unknown Genre'} Elements",
            "genre_element",
            dependencies=("setting_rules", "places", "groups"),
            fields=(
                _field("name", required=True),
                _field("function_in_setting", required=True),
                _field("dependency", required=True),
                _field("current_pressure", required=True),
                _field("observable_evidence", "structured_object", required=True),
            ),
            target_range=DomainTargetRange((3, 4), (5, 8), (9, 14)),
            generation_guidance={
                "requested_genre": genre,
                "description": description,
                "campaign_mode": campaign_mode,
                "instruction": "Generate setting-specific concepts; do not import unrelated genre defaults.",
            },
        )
        return GenreProfile(
            profile_id=f"world_local:{normalized}",
            version=1,
            display_name=genre.strip() or "Unknown genre",
            aliases=(genre,),
            domains=(*_core_domains(), concept_domain),
            genre_tags=(normalized,),
            launch_requirements=LaunchRequirements(
                required_domain_ids=(
                    "setting_rules",
                    "places",
                    "groups",
                    "actors",
                    "pressures",
                    "opening_threads",
                ),
            ),
            provenance={
                "source": "world_local_profile_generator_v1",
                "requested_description": description,
                "campaign_mode": campaign_mode,
            },
            scope="world_local",
        ).require_valid()


def resolve_or_generate_genre_profile(
    *,
    genre: str,
    description: str = "",
    campaign_mode: str = "persistent_living_world",
    registry: GenreProfileRegistry | None = None,
    generator: GenreProfileGenerator | None = None,
) -> ProfileResolution:
    resolved_registry = registry or default_profile_registry()
    existing = resolved_registry.resolve(genre)
    if existing is not None:
        return ProfileResolution(
            profile=existing,
            source="registry",
            requested_genre=genre,
            normalized_genre=normalize_genre_key(genre),
            generated=False,
        )
    generated = (generator or HeuristicWorldLocalProfileGenerator()).generate_profile(
        genre=genre,
        description=description,
        campaign_mode=campaign_mode,
    ).require_valid()
    if generated.scope != "world_local":
        generated = replace(generated, scope="world_local")
    return ProfileResolution(
        profile=generated,
        source="generated_world_local",
        requested_genre=genre,
        normalized_genre=normalize_genre_key(genre),
        generated=True,
    )
