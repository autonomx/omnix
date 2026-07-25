import pytest

from app.rpg.session.genesis.world_forge_profile_generation import (
    STANDARD_DOMAIN_IDS,
    default_profile_registry,
)
from app.rpg.session.genesis.world_forge_profile_graph import build_profile_topic_graph
from app.rpg.worlds.authoring_presentations import section_page_kind
from app.rpg.worlds.profile_authoring import (
    profile_review_from_world,
    require_approved_profile,
)
from app.rpg.worlds.profile_aware_world_images import _profile_targets


def _world(profile, *, approved: bool) -> dict:
    return {
        "id": "world:cyber",
        "genre": "cyberpunk",
        "metadata": {
            "genre_profile_binding": {
                "status": "ready",
                "profile": profile.as_dict(),
                "profile_hash": profile.content_hash,
                "approved_profile_hash": profile.content_hash if approved else "",
                "profile_revision": 1,
            }
        },
    }


def test_cyberpunk_flavours_complete_standard_catalogue() -> None:
    profile = default_profile_registry().resolve("cyberpunk")
    assert profile is not None
    domains = profile.domain_map()

    assert set(STANDARD_DOMAIN_IDS) == set(domains)
    assert domains["actors"].title == "Actors and NPCs"
    assert domains["groups"].title == "Corporations, Gangs, Governments and Institutions"
    assert domains["networks"].title == "Networks, Virtual Spaces and Artificial Intelligences"
    assert domains["technology_augmentations"].title == "Technology and Augmentations"
    assert domains["quests"].title == "Quests, Jobs and Contracts"

    actors_presentation = domains["actors"].generation_guidance["presentation"]
    places_presentation = domains["places"].generation_guidance["presentation"]
    assert actors_presentation == {
        "page_kind": "collection",
        "card_variant": "npcs",
        "image_role": "portrait",
        "group": "world",
    }
    assert places_presentation["page_kind"] == "collection"
    assert places_presentation["image_role"] == "scene"


def test_profile_graph_projects_collection_categories() -> None:
    profile = default_profile_registry().resolve("cyberpunk")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="open_world")

    assert graph.graph_version == "rpg_profile_topic_graph_v2"
    assert graph.node_map()["actors"].category == "actors"
    assert graph.node_map()["places"].category == "places"
    assert graph.node_map()["setting_rules"].category == "lore"
    assert section_page_kind(graph.node_map()["actors"].category) == "collection"
    assert section_page_kind(graph.node_map()["places"].category) == "collection"
    assert section_page_kind(graph.node_map()["setting_rules"].category) == "document"


def test_ready_profile_requires_explicit_approval_hash() -> None:
    profile = default_profile_registry().resolve("cyberpunk")
    assert profile is not None
    pending_world = _world(profile, approved=False)
    approved_world = _world(profile, approved=True)

    assert profile_review_from_world(pending_world)["status"] == "review_required"
    with pytest.raises(ValueError, match="world_profile_approval_required"):
        require_approved_profile(pending_world)

    review = require_approved_profile(approved_world)
    assert review["status"] == "approved"
    assert review["approved_profile_hash"] == profile.content_hash


def test_profile_image_roles_create_actor_and_place_targets() -> None:
    profile = default_profile_registry().resolve("cyberpunk")
    assert profile is not None
    detail = {
        "world": _world(profile, approved=True),
        "topics": [
            {
                "topic_id": "actors",
                "content": {
                    "entities": [
                        {
                            "id": "actor:runner",
                            "kind": "actor",
                            "name": "Mara Vex",
                            "short_summary": "A courier hunted by corporate security.",
                        }
                    ]
                },
            },
            {
                "topic_id": "places",
                "content": {
                    "entities": [
                        {
                            "id": "place:night_market",
                            "kind": "place",
                            "name": "The Night Market",
                            "short_summary": "A rain-soaked bazaar beneath the maglev lines.",
                        }
                    ]
                },
            },
        ],
    }

    targets = {target["target_id"]: target for target in _profile_targets(detail)}
    assert targets["entity:actor:runner:portrait"]["role"] == "portrait"
    assert targets["entity:place:night_market:scene"]["role"] == "scene"
    assert targets["entity:place:night_market:map"]["role"] == "map"
