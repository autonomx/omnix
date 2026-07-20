from __future__ import annotations

from app.rpg.session.genesis.world_forge_contract import build_campaign_topic_graph
from app.rpg.session.genesis.world_forge_default import ReferenceSafeWorldForgeGenerator
from app.rpg.session.genesis.world_forge_domains import (
    DOMAIN_SPECS,
    validate_structured_domain,
)


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
