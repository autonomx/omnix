from __future__ import annotations

import pytest

from app.rpg.session.genesis.world_forge_contract import (
    CampaignTopicNode,
    build_campaign_topic_graph,
)
from app.rpg.session.genesis.world_forge_default import ReferenceSafeWorldForgeGenerator
from app.rpg.session.genesis.world_forge_domains import (
    DOMAIN_SPECS,
    normalize_structured_domain,
    validate_structured_domain,
    validate_world_brief_grounding,
)
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic


def test_expanded_graph_contains_gameplay_and_scenario_domains() -> None:
    graph = build_campaign_topic_graph(
        campaign_template="classic_fantasy",
        genre="fantasy",
        tone="heroic",
        depth="quick",
        background_expansion=False,
    )
    nodes = graph.node_map()

    assert set(DOMAIN_SPECS).issubset(nodes)
    assert nodes["points_of_interest"].dependencies == (
        "locations",
        "regions",
        "history",
        "current_conflicts",
    )
    assert nodes["quests"].dependencies == (
        "current_conflicts",
        "npcs",
        "locations",
        "factions",
        "points_of_interest",
    )
    assert nodes["one_shots"].dependencies == (
        "quests",
        "opening_threads",
        "npcs",
        "locations",
        "encounter_seeds",
    )
    assert graph.validate() == ()


def test_deterministic_generator_produces_valid_structured_domain_entities() -> None:
    graph = build_campaign_topic_graph(
        campaign_template="classic_fantasy",
        genre="fantasy",
        tone="heroic",
        depth="quick",
        starting_location="rusty_flagon_tavern",
        background_expansion=False,
    )
    generator = ReferenceSafeWorldForgeGenerator()
    generated = {}

    for node in graph.topological_order():
        if node.category in {"compiler", "audit", "index", "bootstrap"}:
            continue
        dependencies = {
            dependency_id: generated[dependency_id]
            for dependency_id in node.dependencies
            if dependency_id in generated
        }
        topic = generator.generate(
            node,
            seed=77,
            campaign_context={
                "campaign_template": "classic_fantasy",
                "starting_location": "rusty_flagon_tavern",
            },
            dependency_topics=dependencies,
        )
        generated[node.topic_id] = topic
        validate_structured_domain(node, topic, dependencies)

    for topic_id, spec in DOMAIN_SPECS.items():
        topic = generated[topic_id]
        assert len(topic.entities) == graph.node_map()[topic_id].target_count
        assert all(entity["kind"] == spec.kind for entity in topic.entities)
        assert len({entity["id"] for entity in topic.entities}) == len(topic.entities)
        assert topic.documents
        assert topic.facts


def test_live_structured_domain_rejects_missing_entities_instead_of_padding() -> None:
    node = CampaignTopicNode(
        topic_id="races",
        title="Races and Ancestries",
        category="races",
        target_count=2,
    )
    with pytest.raises(ValueError, match="structured_domain_count:races:1:2"):
        normalize_structured_domain(
            node,
            GeneratedTopic(
                topic_id="races",
                entities=({"name": "Vault Dweller"},),
            ),
            {},
            allow_synthetic_completion=False,
        )


def test_domain_references_resolve_dependency_topic_names_to_stable_ids() -> None:
    node = CampaignTopicNode(
        topic_id="classes",
        title="Classes and Disciplines",
        category="classes",
        target_count=1,
    )
    dependencies = {
        "institutions": GeneratedTopic(
            topic_id="institutions",
            entities=(
                {
                    "id": "ent:institutions:001",
                    "name": "Wasteland Rangers",
                    "kind": "lore",
                },
            ),
        ),
    }

    normalized = normalize_structured_domain(
        node,
        GeneratedTopic(
            topic_id="classes",
            entities=(
                {
                    "id": "class:wasteland_gunslinger",
                    "name": "Wasteland Gunslinger",
                    "capabilities": ["scavenging", "precise fire"],
                    "progression": ["novice", "veteran"],
                    "equipment": ["custom rifle"],
                    "institution_ids": ["Wasteland Rangers"],
                },
            ),
        ),
        dependencies,
        allow_synthetic_completion=False,
    )

    assert normalized.entities[0]["institution_ids"] == ["ent:institutions:001"]
    validate_structured_domain(node, normalized, dependencies)


def test_world_brief_grounding_rejects_generic_placeholder_canon() -> None:
    node = CampaignTopicNode(
        topic_id="races",
        title="Races and Ancestries",
        category="races",
        target_count=1,
    )
    topic = GeneratedTopic(
        topic_id="races",
        entities=({"id": "race:placeholder", "name": "Races and Ancestrie 1"},),
    )
    with pytest.raises(ValueError, match="world_generation_placeholder_entity:races"):
        validate_world_brief_grounding(
            node,
            topic,
            {
                "world_brief": {
                    "title": "Fallout",
                    "description": "A nuclear wasteland of Vaults, mutants, and irradiated deserts.",
                }
            },
        )

    generic_topic = GeneratedTopic(
        topic_id="races",
        entities=({"id": "race:elf", "name": "Elves", "description": "Magic beings."},),
    )
    with pytest.raises(ValueError, match="world_brief_grounding:races:0:3"):
        validate_world_brief_grounding(
            node,
            generic_topic,
            {
                "world_brief": {
                    "title": "Fallout",
                    "description": "A nuclear wasteland of Vaults, mutants, and irradiated deserts.",
                }
            },
        )
