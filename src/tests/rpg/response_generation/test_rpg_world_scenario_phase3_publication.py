from __future__ import annotations

from app.rpg.session.genesis.world_forge_contract import (
    CampaignTopicGraph,
    CampaignTopicNode,
)
from app.rpg.session.genesis.world_forge_default import ReferenceSafeWorldForgeGenerator
from app.rpg.session.genesis.world_forge_deterministic import DeterministicWorldForgeGenerator
from app.rpg.session.genesis.world_forge_generation import generate_campaign_topics
from app.rpg.worlds.generation_jobs import canonical_hash
from app.rpg.worlds.generation_publication import (
    compile_world_generation_publication,
)


def _graph() -> CampaignTopicGraph:
    return CampaignTopicGraph(
        graph_version="world-publication-test-v1",
        campaign_template="classic_fantasy",
        depth="quick",
        nodes=(
            CampaignTopicNode(
                topic_id="realm",
                title="Realm",
                category="lore",
                generator_role="realm_architect",
            ),
            CampaignTopicNode(
                topic_id="regions",
                title="Regions",
                category="regions",
                dependencies=("realm",),
                generator_role="geography_architect",
                target_count=2,
            ),
        ),
    )


def test_completed_topics_compile_to_hashed_revision_and_release() -> None:
    graph = _graph()
    generated = generate_campaign_topics(
        graph,
        generator=ReferenceSafeWorldForgeGenerator(DeterministicWorldForgeGenerator()),
        seed=17,
        campaign_context={
            "world_id": "world:durable",
            "genre": "classic_fantasy",
            "tone": "mythic",
            "starting_location": "location:harbor",
        },
    )
    topic_rows = [
        {
            "topic_id": topic.topic_id,
            "status": "ready",
            "content": topic.as_dict(),
            "content_hash": canonical_hash(topic.as_dict()),
        }
        for topic in generated.topics
    ]
    publication = compile_world_generation_publication(
        run={
            "run_id": "world-generation:durable:draft:1",
            "draft_revision": 1,
            "graph": graph.as_dict(),
            "context": {
                "generation_context": {
                    "starting_location": "location:harbor",
                }
            },
            "settings": {
                "generator_version": "deterministic-v1",
                "prompt_version": "test-prompt-v1",
            },
        },
        world={
            "id": "world:durable",
            "title": "Durable World",
            "metadata": {},
        },
        topic_rows=topic_rows,
        revision=1,
    )

    assert publication.world_revision.world_id == "world:durable"
    assert publication.world_revision.revision == 1
    assert publication.world_revision.content_hash.startswith("sha256:")
    assert publication.world_release.world_revision_hash == publication.world_revision.content_hash
    assert publication.world_release.release_hash.startswith("sha256:")
    assert publication.world_release.certification["generation_run_id"] == "world-generation:durable:draft:1"
    assert publication.world_release.certification["launch_ready"] is False
    assert publication.world_release.certification["missing_requirements"]
