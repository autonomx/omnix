from __future__ import annotations

import pytest

from app.rpg.session.genesis.world_forge_profile_generation import STANDARD_DOMAIN_IDS
from app.rpg.session.genesis.world_forge_profile_provider import (
    GenreProfileProposalResponse,
    ProfileDomainResponse,
    ProfileFieldResponse,
    ProfileTargetRangeResponse,
    profile_from_proposal,
)
from app.rpg.worlds.generation_routing import ResolvedWorldForgeRoute
from app.rpg.worlds.profile_authoring import profile_review_from_world
from app.rpg.worlds.profile_generation_jobs import (
    WORLD_PROFILE_JOB_TYPE,
    plan_world_profile_creation,
    profile_manifest_run,
    profile_resolution_from_world,
)


def _route() -> ResolvedWorldForgeRoute:
    return ResolvedWorldForgeRoute(
        provider="lmstudio",
        model="qwen-test",
        source="settings_control_center",
        requested_provider="configured",
        requested_model="configured",
    )


def test_known_genre_binds_profile_without_provider_job_but_requires_review() -> None:
    plan = plan_world_profile_creation(
        world_id="world:cyberpunk",
        title="Cyberpunk 2099",
        genre="cyberpunk",
        description="A corporate neon dystopia.",
        tone="noir",
        campaign_mode="persistent_living_world",
        seed=7,
        route=_route(),
    )

    assert plan.job_payload is None
    assert plan.binding["status"] == "ready"
    assert plan.binding["profile_id"] == "cyberpunk"
    assert plan.binding["source"] == "registry"
    assert not plan.binding.get("approved_profile_hash")
    review = profile_review_from_world(
        {
            "id": "world:cyberpunk",
            "genre": "cyberpunk",
            "metadata": {"genre_profile_binding": dict(plan.binding)},
        }
    )
    assert review["status"] == "review_required"


def test_unknown_genre_queues_durable_llm_profile_job() -> None:
    plan = plan_world_profile_creation(
        world_id="world:abyss",
        title="The Drowned Court",
        genre="underwater biopunk political tragedy",
        description="A pressure-bound empire grown from living architecture.",
        tone="tragic intrigue",
        campaign_mode="political_mystery",
        seed=11,
        route=_route(),
    )

    assert plan.binding["status"] == "generating"
    assert plan.binding["route"] == {
        "provider": "lmstudio",
        "model": "qwen-test",
        "source": "settings_control_center",
    }
    assert plan.job_payload is not None
    assert plan.job_payload["job_type"] == WORLD_PROFILE_JOB_TYPE
    assert plan.job_payload["input_payload"]["settings"]["provider_route"] == "lmstudio"
    assert plan.job_payload["input_payload"]["profile_input"]["description"].startswith(
        "A pressure-bound empire"
    )


def test_llm_profile_proposal_compiles_with_standard_and_setting_domains() -> None:
    proposal = GenreProfileProposalResponse(
        display_name="Underwater biopunk political tragedy",
        aliases=["abyssal biopunk"],
        genre_tags=["biopunk", "underwater", "political"],
        domains=[
            ProfileDomainResponse(
                domain_id="oxygen_economy",
                title="Oxygen Economy",
                entity_kind="oxygen_resource",
                dependencies=["places", "groups"],
                fields=[
                    ProfileFieldResponse(field_id="name", required=True),
                    ProfileFieldResponse(
                        field_id="controller_group_ids",
                        value_type="entity_ref_list",
                        allowed_target_domains=["groups"],
                    ),
                    ProfileFieldResponse(field_id="scarcity", required=True),
                ],
                target_range=ProfileTargetRangeResponse(
                    quick=(2, 3), standard=(4, 6), epic=(7, 10)
                ),
            ),
            ProfileDomainResponse(
                domain_id="living_architecture",
                title="Living Architecture",
                entity_kind="grown_structure",
                dependencies=["places", "setting_rules"],
                fields=[
                    ProfileFieldResponse(field_id="name", required=True),
                    ProfileFieldResponse(
                        field_id="place_id",
                        value_type="entity_ref",
                        allowed_target_domains=["places"],
                    ),
                    ProfileFieldResponse(field_id="biological_need", required=True),
                ],
            ),
        ],
        runtime_capability_defaults={"resource_simulation": True},
        rationale="The setting revolves around biological infrastructure and breathable air.",
    )

    profile = profile_from_proposal(
        proposal,
        genre="underwater biopunk political tragedy",
        description="A pressure-bound empire grown from living architecture.",
        campaign_mode="political_mystery",
    )
    domains = profile.domain_map()

    assert set(STANDARD_DOMAIN_IDS).issubset(domains)
    assert {"oxygen_economy", "living_architecture"}.issubset(domains)
    assert "spells" not in domains
    assert "pantheon" not in domains
    assert profile.scope == "world_local"
    assert profile.validate() == ()


def test_profile_proposal_cannot_redefine_core_domain() -> None:
    proposal = GenreProfileProposalResponse(
        display_name="Invalid",
        domains=[
            ProfileDomainResponse(
                domain_id="actors",
                title="Replacement Actors",
                entity_kind="replacement_actor",
            )
        ],
        rationale="Invalid replacement.",
    )
    with pytest.raises(ValueError, match="redefines_core_domain"):
        profile_from_proposal(
            proposal,
            genre="invalid",
            description="",
            campaign_mode="persistent_living_world",
        )


def test_pending_profile_manifest_hides_lore_domains() -> None:
    plan = plan_world_profile_creation(
        world_id="world:pending",
        title="Pending",
        genre="unknown dream ecology",
        description="A world of migrating dreams.",
        tone="surreal",
        campaign_mode="sandbox",
        seed=3,
        route=_route(),
    )
    world = {
        "id": "world:pending",
        "draft_revision": 1,
        "genre": "unknown dream ecology",
        "tone": "surreal",
        "metadata": {"genre_profile_binding": dict(plan.binding)},
    }

    run = profile_manifest_run(world)
    assert run is not None
    assert run["status"] == "running"
    assert [node["category"] for node in run["graph"]["nodes"]] == ["bootstrap"]
    with pytest.raises(ValueError, match="world_profile_not_ready:generating"):
        profile_resolution_from_world(world)


def test_ready_profile_manifest_uses_pinned_cyberpunk_standard_graph() -> None:
    plan = plan_world_profile_creation(
        world_id="world:ready",
        title="Cyberpunk 2099",
        genre="cyberpunk",
        description="Corporate neon dystopia.",
        tone="noir",
        campaign_mode="persistent_living_world",
        seed=9,
        route=_route(),
    )
    world = {
        "id": "world:ready",
        "draft_revision": 1,
        "genre": "cyberpunk",
        "tone": "noir",
        "metadata": {
            "campaign_template": "cyberpunk",
            "genre_profile_binding": dict(plan.binding),
        },
    }

    run = profile_manifest_run(world)
    assert run is not None
    ids = {node["topic_id"] for node in run["graph"]["nodes"]}
    assert set(STANDARD_DOMAIN_IDS).issubset(ids)
    assert {"networks", "technology_augmentations", "places", "actors"}.issubset(ids)
    assert {"spells", "pantheon", "hero_system"}.isdisjoint(ids)
    actors = next(node for node in run["graph"]["nodes"] if node["topic_id"] == "actors")
    assert actors["metadata"]["presentation"]["page_kind"] == "collection"
    assert actors["metadata"]["presentation"]["image_role"] == "portrait"
